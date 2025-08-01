GMGN-Trading-Bot
A Python-based automated trading bot integrated with the GMGN trading platform on Solana. The bot uses a multiplier-based sell strategy (selling at 2x and 3x price increases), validates tokens via Rugcheck API, fetches price data from Binance, and executes live trades through GMGN's API with Telegram-based authentication.
Features

Multiplier Sell Strategy: Automatically buys tokens and sells 50% at 2x and 100% at 3x price multipliers.
Rugcheck Integration: Validates token safety using Rugcheck API, only trading tokens rated "GOOD".
GMGN API Support: Executes live buy/sell orders on Solana via GMGN's trading API.
Telegram Authentication: Securely connects to GMGN using Telegram bot login.
Binance Price Data: Fetches real-time OHLCV data from Binance for strategy decisions.
Configurable Risk Management: Adjustable allocation per trade and sell percentages.
Error Handling & Logging: Comprehensive logging for monitoring and debugging.

Prerequisites

Python 3.8 or higher
A Binance account with API keys
A Rugcheck API key from Rugcheck.xyz
A Solana wallet with funds for trading and transaction fees
A Telegram bot token and chat ID for GMGN authentication

Installation

Clone the Repository:
git clone https://github.com/your-username/GMGN-Trading-Bot.git
cd GMGN-Trading-Bot


Install Dependencies:Install required Python packages using pip:
pip install ccxt pyyaml requests python-telegram-bot solders solana



Configuration

Create Configuration File:Copy the provided config.yaml template to the project directory and update it with your settings:
cp config.yaml.example config.yaml


Update config.yaml:Edit config.yaml with the following details:

Binance API:
api_key: Your Binance API key
api_secret: Your Binance API secret


Rugcheck API:
rugcheck_api_key: Your Rugcheck API key


GMGN API:
private_key: Your Solana wallet's private key (base58-encoded)
api_host: GMGN API endpoint (default: https://gmgn.ai)
chain: Blockchain (default: sol)
rpc_endpoint: Solana RPC endpoint (default: https://api.mainnet-beta.solana.com)


Telegram:
bot_token: Telegram bot token from BotFather
chat_id: Your Telegram chat ID (use @get_id_bot to find it)


Trading Parameters:
symbols: Trading pairs (e.g., BTC/USDT, ETH/USDT)
timeframe: Price data timeframe (e.g., 1h)
max_allocation_percent: Max % of balance per trade (default: 10.0)
sell_percent_2x: % to sell at 2x multiplier (default: 50.0)
sell_percent_3x: % to sell at 3x multiplier (default: 100.0)




Update Token Mappings:In trading_bot.py, update the chain_mapping dictionary in the TradingBot class:

Replace BTC_ADDRESS and ETH_ADDRESS with actual Solana token contract addresses for your trading pairs.
Ensure gmgn_token_in is set to the correct input token (e.g., WSOL for SOL).

Example:
'BTC/USDT': {
    'chain': 'bitcoin',
    'contract_address': 'BTC',
    'gmgn_token_in': 'So11111111111111111111111111111111111111112',
    'gmgn_token_out': 'YOUR_BTC_TOKEN_ADDRESS'
}



Usage

Run the Bot:Execute the bot from the project directory:
python trading_bot.py

The bot will:

Load configuration
Authenticate with GMGN via Telegram
Validate tokens using Rugcheck API
Fetch price data from Binance
Execute the multiplier sell strategy
Submit trades via GMGN API


Monitor Logs:Check console output for logs:

INFO: Normal operations (e.g., trade decisions, executions)
WARNING: Issues like failed Rugcheck validations
ERROR: Critical errors (e.g., API failures)


Stop the Bot:Press Ctrl+C to gracefully stop the bot, closing exchange and Solana connections.


Testing

Paper Trading: Use a Solana testnet RPC endpoint (rpc_endpoint: https://api.testnet.solana.com) and a test wallet.
Low Risk: Start with a small max_allocation_percent (e.g., 1-2%) and limited funds.
Verify Setup: Ensure all API keys, token addresses, and Telegram settings are correct before trading live.

Security Notes

Sensitive Data: Store API keys, private keys, and Telegram tokens securely (e.g., as environment variables).
Wallet Safety: Use a dedicated Solana wallet with minimal funds for trading.
Key Rotation: Regularly rotate API keys and monitor wallet activity.
Backup: Securely back up your configuration and private key.

Troubleshooting

Authentication Errors: Verify Telegram bot token and chat ID. Ensure the bot is started in your Telegram chat.
API Errors: Check API keys and network connectivity. Confirm Rugcheck and GMGN API endpoints are accessible.
Transaction Failures: Ensure sufficient SOL for fees and correct token addresses in chain_mapping.
Logs: Review log messages for detailed error information.

Contributing
Contributions are welcome! Please:

Fork the repository
Create a feature branch
Submit a pull request with clear descriptions

License
This project is licensed under the MIT License. See the LICENSE file for details.
Acknowledgments

ccxt for exchange data
Rugcheck.xyz for token validation
GMGN.ai for trading API
python-telegram-bot for Telegram integration
solana-py and solders for Solana interactions
