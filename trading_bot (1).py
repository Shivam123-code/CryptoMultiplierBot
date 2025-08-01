import os
import json
import logging
import ccxt.async_support as ccxt
from typing import Dict, Any, Optional
import asyncio
import yaml
import requests
from telegram import Bot
from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solana.keypair import Keypair
from solders.transaction import VersionedTransaction
import base64

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConfigManager:
    """Handles configuration loading and validation"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        """Initialize with path to config file"""
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load and validate configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as file:
                config = yaml.safe_load(file)
                required_keys = [
                    'exchange', 'api_key', 'api_secret', 'rugcheck_api_key',
                    'symbols', 'timeframe', 'strategy', 'max_allocation_percent',
                    'sell_percent_2x', 'sell_percent_3x', 'gmgn_api', 'telegram'
                ]
                if not all(key in config for key in required_keys):
                    raise ValueError("Missing required configuration keys")
                return config
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            raise

class RugcheckClient:
    """Handles Rugcheck API interactions for token validation"""
    
    def __init__(self, api_key: str):
        """Initialize with Rugcheck API key"""
        self.api_key = api_key
        self.base_url = "https://api.rugcheck.xyz"
    
    async def validate_token(self, chain: str, contract_address: str) -> Dict[str, Any]:
        """Validate token using Rugcheck API"""
        try:
            endpoint = f"/tokens/scan/{chain}/{contract_address}"
            headers = {'X-API-KEY': self.api_key}
            params = {
                "includeDexScreenerData": "true",
                "includeSignificantEvents": "false"
            }
            
            response = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: requests.get(f"{self.base_url}{endpoint}", headers=headers, params=params)
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'is_valid': data.get('riskLevel', '').upper() == 'GOOD',
                    'risk_level': data.get('riskLevel', 'UNKNOWN'),
                    'details': data
                }
            else:
                logger.error(f"Rugcheck API error: {response.status_code} - {response.text}")
                return {
                    'is_valid': False,
                    'risk_level': 'ERROR',
                    'details': {'error': response.text}
                }
        except Exception as e:
            logger.error(f"Failed to validate token {contract_address}: {str(e)}")
            return {
                'is_valid': False,
                'risk_level': 'ERROR',
                'details': {'error': str(e)}
            }

class GMGNClient:
    """Handles GMGN API interactions and Telegram login"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with GMGN and Telegram configuration"""
        self.api_host = config['gmgn_api']['api_host']
        self.chain = config['gmgn_api']['chain']
        self.telegram_token = config['telegram']['bot_token']
        self.telegram_bot = Bot(token=self.telegram_token)
        self.solana_client = AsyncClient(config['gmgn_api']['rpc_endpoint'])
        self.wallet = Keypair.from_secret_key(
            base58.decode(config['gmgn_api']['private_key'])
        ) if config['gmgn_api'].get('private_key') else None
        self.authenticated = False
    
    async def authenticate_telegram(self, chat_id: int) -> bool:
        """Authenticate with GMGN via Telegram bot"""
        try:
            await self.telegram_bot.send_message(
                chat_id=chat_id,
                text="/start"
            )
            wallet_address = self.wallet.public_key.to_base58().decode() if self.wallet else "generated_wallet"
            logger.info(f"Authenticated with Telegram, wallet address: {wallet_address}")
            self.authenticated = True
            return True
        except Exception as e:
            logger.error(f"Telegram authentication failed: {str(e)}")
            return False
    
    async def get_swap_route(self, token_in: str, token_out: str, amount: str, slippage: float = 0.5) -> Optional[Dict]:
        """Get swap route from GMGN API"""
        try:
            url = (
                f"{self.api_host}/defi/router/v1/{self.chain}/tx/get_swap_route"
                f"?token_in_address={token_in}&token_out_address={token_out}"
                f"&in_amount={amount}&from_address={self.wallet.public_key.to_base58().decode()}"
                f"&slippage={slippage}"
            )
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(url)
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get swap route: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting swap route: {str(e)}")
            return None
    
    async def submit_transaction(self, signed_tx: str) -> Optional[Dict]:
        """Submit signed transaction to GMGN API"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.api_host}/txproxy/v1/send_transaction",
                    headers={'content-type': 'application/json'},
                    json={"chain": self.chain, "signedTx": signed_tx}
                )
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to submit transaction: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error submitting transaction: {str(e)}")
            return None
    
    async def execute_swap(self, token_in: str, token_out: str, amount: str, side: str) -> Optional[Dict]:
        """Execute buy or sell order via GMGN API"""
        if not self.authenticated:
            logger.error("GMGN client not authenticated")
            return None
        
        route = await self.get_swap_route(token_in, token_out, amount)
        if not route or 'data' not in route or 'raw_tx' not in route['data']:
            logger.error("Invalid swap route response")
            return None
        
        try:
            swap_tx_buf = base64.b64decode(route['data']['raw_tx']['swapTransaction'])
            transaction = VersionedTransaction.from_bytes(swap_tx_buf)
            transaction.sign([self.wallet])
            signed_tx = base64.b64encode(transaction.serialize()).decode()
            
            result = await self.submit_transaction(signed_tx)
            if result and 'data' in result and 'hash' in result['data']:
                logger.info(f"Executed {side} order: {result['data']['hash']}")
                return result
            return None
        except Exception as e:
            logger.error(f"Failed to execute swap: {str(e)}")
            return None

class ExchangeClient:
    """Manages exchange connection and token fetching for price data"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with exchange configuration"""
        self.config = config
        self.exchange = self._initialize_exchange()
    
    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize exchange connection"""
        try:
            exchange_class = getattr(ccxt, self.config['exchange'])
            exchange = exchange_class({
                'apiKey': self.config['api_key'],
                'secret': self.config['api_secret'],
                'enableRateLimit': True,
            })
            return exchange
        except Exception as e:
            logger.error(f"Failed to initialize exchange: {str(e)}")
            raise
    
    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list:
        """Fetch OHLCV data for a given symbol"""
        try:
            await self.exchange.load_markets()
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {str(e)}")
            return []
    
    async def fetch_balance(self) -> Dict[str, Any]:
        """Fetch account balance"""
        try:
            balance = await self.exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"Failed to fetch balance: {str(e)}")
            return {}

class TradingStrategy:
    """Base class for trading strategies"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with strategy configuration"""
        self.config = config
    
    async def execute(self, data: list, position: Dict[str, Any]) -> Dict[str, Any]:
        """Placeholder for strategy execution"""
        return {'action': 'hold', 'amount': 0.0}

class MultiplierSellStrategy(TradingStrategy):
    """Strategy that auto-sells at 2x and 3x price multipliers"""
    
    def __init__(self, config: Dict[str, Any], exchange_client: ExchangeClient):
        """Initialize with config and exchange client"""
        super().__init__(config)
        self.exchange_client = exchange_client
        self.position_tracker = {}
    
    async def execute(self, data: list, position: Dict[str, Any]) -> Dict[str, Any]:
        """Execute multiplier-based selling strategy"""
        if not data:
            return {'action': 'hold', 'amount': 0.0}
        
        symbol = position.get('symbol')
        current_price = data[-1][4]
        position_amount = position.get('amount', 0.0)
        
        if symbol not in self.position_tracker:
            self.position_tracker[symbol] = {
                'entry_price': current_price if position_amount > 0 else 0.0,
                'amount': position_amount
            }
        
        self.position_tracker[symbol]['amount'] = position_amount
        
        if position_amount == 0.0:
            balance = await self.exchange_client.fetch_balance()
            quote_currency = symbol.split('/')[1]
            available_balance = balance.get(quote_currency, {}).get('free', 0.0)
            
            max_allocation = available_balance * (self.config['max_allocation_percent'] / 100)
            amount_to_buy = max_allocation / current_price
            
            if amount_to_buy > 0:
                self.position_tracker[symbol]['entry_price'] = current_price
                logger.info(f"Buying {amount_to_buy} of {symbol} at {current_price}")
                return {'action': 'buy', 'amount': amount_to_buy}
        
        entry_price = self.position_tracker[symbol]['entry_price']
        if entry_price > 0:
            price_multiplier = current_price / entry_price
            
            if price_multiplier >= 3.0 and position_amount > 0:
                sell_amount = position_amount * (self.config['sell_percent_3x'] / 100)
                logger.info(f"Selling {sell_amount} of {symbol} at 3x multiplier ({current_price})")
                return {'action': 'sell', 'amount': sell_amount}
            elif price_multiplier >= 2.0 and position_amount > 0:
                sell_amount = position_amount * (self.config['sell_percent_2x'] / 100)
                logger.info(f"Selling {sell_amount} of {symbol} at 2x multiplier ({current_price})")
                return {'action': 'sell', 'amount': sell_amount}
        
        return {'action': 'hold', 'amount': 0.0}

class TradingBot:
    """Main trading bot class orchestrating all components"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        """Initialize bot components"""
        self.config_manager = ConfigManager(config_path)
        self.rugcheck_client = RugcheckClient(self.config_manager.config['rugcheck_api_key'])
        self.exchange_client = ExchangeClient(self.config_manager.config)
        self.gmgn_client = GMGNClient(self.config_manager.config)
        self.strategy = MultiplierSellStrategy(self.config_manager.config, self.exchange_client)
        self.running = False
        self.chain_mapping = {
            'BTC/USDT': {
                'chain': 'bitcoin',
                'contract_address': 'BTC',
                'gmgn_token_in': 'So11111111111111111111111111111111111111112',
                'gmgn_token_out': 'BTC_ADDRESS'  # Replace with actual token address
            },
            'ETH/USDT': {
                'chain': 'ethereum',
                'contract_address': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
                'gmgn_token_in': 'So11111111111111111111111111111111111111112',
                'gmgn_token_out': 'ETH_ADDRESS'  # Replace with actual token address
            }
        }
    
    async def initialize(self):
        """Initialize bot with GMGN Telegram authentication"""
        if not await self.gmgn_client.authenticate_telegram(
            self.config_manager.config['telegram']['chat_id']
        ):
            raise RuntimeError("Failed to authenticate with GMGN Telegram")
    
    async def validate_token_safety(self, symbol: str) -> bool:
        """Validate token safety using Rugcheck API"""
        if symbol not in self.chain_mapping:
            logger.error(f"No chain mapping for symbol {symbol}")
            return False
        
        chain_info = self.chain_mapping[symbol]
        validation_result = await self.rugcheck_client.validate_token(
            chain_info['chain'],
            chain_info['contract_address']
        )
        
        if validation_result['is_valid']:
            logger.info(f"Token {symbol} passed Rugcheck validation (Risk Level: GOOD)")
            return True
        else:
            logger.warning(
                f"Token {symbol} failed Rugcheck validation. "
                f"Risk Level: {validation_result['risk_level']}, "
                f"Details: {validation_result['details']}"
            )
            return False
    
    async def run(self):
        """Main bot execution loop"""
        await self.initialize()
        self.running = True
        logger.info("Starting trading bot...")
        
        while self.running:
            try:
                for symbol in self.config_manager.config['symbols']:
                    if not await self.validate_token_safety(symbol):
                        logger.info(f"Skipping {symbol} due to failed Rugcheck validation")
                        continue
                        
                    data = await self.exchange_client.fetch_ohlcv(
                        symbol,
                        self.config_manager.config['timeframe']
                    )
                    
                    if data:
                        balance = await self.exchange_client.fetch_balance()
                        base_currency = symbol.split('/')[0]
                        position = {
                            'symbol': symbol,
                            'amount': balance.get(base_currency, {}).get('free', 0.0)
                        }
                        
                        decision = await self.strategy.execute(data, position)
                        logger.info(f"Decision for {symbol}: {decision}")
                        
                        await self._execute_trade(symbol, decision)
                    
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                await asyncio.sleep(5)
    
    async def _execute_trade(self, symbol: str, decision: Dict[str, Any]):
        """Execute trades via GMGN API"""
        try:
            if decision['action'] not in ['buy', 'sell'] or decision['amount'] <= 0:
                logger.info(f"No trade executed for {symbol}: {decision}")
                return
            
            chain_info = self.chain_mapping.get(symbol)
            if not chain_info:
                logger.error(f"No chain mapping for {symbol}")
                return
            
            token_in = chain_info['gmgn_token_in']
            token_out = chain_info['gmgn_token_out']
            
            if decision['action'] == 'sell':
                token_in, token_out = token_out, token_in
            
            amount = str(int(decision['amount'] * 1_000_000))  # Convert to smallest unit
            
            result = await self.gmgn_client.execute_swap(
                token_in=token_in,
                token_out=token_out,
                amount=amount,
                side=decision['action']
            )
            
            if result:
                logger.info(f"Trade executed for {symbol}: {result}")
            else:
                logger.error(f"Trade execution failed for {symbol}")
                
        except Exception as e:
            logger.error(f"Failed to execute trade for {symbol}: {str(e)}")
    
    async def stop(self):
        """Gracefully stop the bot"""
        self.running = False
        await self.exchange_client.exchange.close()
        await self.gmgn_client.solana_client.close()
        logger.info("Trading bot stopped")

async def main():
    """Main entry point for the trading bot"""
    try:
        bot = TradingBot()
        await bot.run()
    except KeyboardInterrupt:
        await bot.stop()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())