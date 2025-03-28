import ccxt
import time
import numpy as np

# OKX Sandbox API Credentials (keep these secure)
API_CREDENTIALS = {
    'apiKey': '544d6587-0a7d-4b73-bb06-0e3656c08a18',
    'secret': '9C2CA165254391E4B4638DE6577288BD',
    'password': '#Dinywa15'
}

def calculate_atr(exchange, symbol, timeframe='1m', period=14):
    """
    Fetch recent candles and calculate the Average True Range (ATR)
    """
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=period+1)
        high_prices = np.array([candle[2] for candle in candles])
        low_prices = np.array([candle[3] for candle in candles])
        close_prices = np.array([candle[4] for candle in candles])
        
        tr = np.maximum(high_prices[1:] - low_prices[1:], 
                        np.abs(high_prices[1:] - close_prices[:-1]),
                        np.abs(low_prices[1:] - close_prices[:-1]))
        atr = np.mean(tr)
        return atr
    except Exception as e:
        print(f"Error calculating ATR: {e}")
        return None

class OKXTrader:
    def __init__(self, api_credentials, symbol='DOGE/USDT:USDT', leverage=5):
        # Configure the exchange for sandbox mode by setting 'sandbox': True
        self.exchange = ccxt.okx({
            'apiKey': api_credentials['apiKey'],
            'secret': api_credentials['secret'],
            'password': api_credentials['password'],
            'enableRateLimit': True,
            'sandbox': True,  # Activate sandbox mode
            'options': {'defaultType': 'swap'}
        })
        self.symbol = symbol
        self.leverage = leverage
        self.contract_size = 1000  # Base contract size for DOGE
        self.setup_trading_params()

    def setup_trading_params(self):
        try:
            # Set leverage using OKX's specific method for swaps
            self.exchange.set_leverage(self.leverage, self.symbol)
            print(f"Leverage set to {self.leverage}x using Cross Margin Mode")
        except Exception as e:
            print(f"Error setting leverage: {e}")

    def get_market_data(self):
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching market data: {e}")
            return None

    def get_open_position(self):
        """
        Fetch open positions to check if there's an existing LONG/SHORT position.
        """
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            for pos in positions:
                if pos['contracts'] > 0:
                    return pos
            return None
        except Exception as e:
            print(f"Error fetching open positions: {e}")
            return None

    def close_position(self, position):
        """
        Close an existing position before opening a new one.
        """
        if position:
            side_to_close = 'sell' if position['side'] == 'long' else 'buy'
            try:
                print(f"Closing {position['side'].upper()} position...")
                self.exchange.create_order(
                    symbol=self.symbol,
                    type='market',
                    side=side_to_close,
                    amount=position['contracts'],
                    params={'tdMode': 'cross'}
                )
                print(f"Closed {position['side'].upper()} position successfully.")
            except Exception as e:
                print(f"Error closing position: {e}")

    def calculate_position_size(self, capital, risk_percentage, stop_loss_pct):
        """
        Calculate position size based on risk management strategy.
        """
        risk_amount = capital * risk_percentage
        position_value = risk_amount / stop_loss_pct
        ticker = self.exchange.fetch_ticker(self.symbol)
        contracts = round(position_value / (self.contract_size * ticker['last']), 2)
        # Ensure a minimum contract size
        return max(contracts * self.contract_size, 0.01)

    def place_order(self, side, size, stop_loss=None, take_profit=None):
        """
        Place a trade and set conditional orders for stop loss and take profit.
        """
        try:
            contracts = round(size / self.contract_size, 2)
            print(f"Placing {side.upper()} order for {contracts} contracts ({size} DOGE)")
            order_params = {
                'posSide': 'long' if side == 'buy' else 'short',
                'tdMode': 'cross'
            }
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=side,
                amount=contracts,
                params=order_params
            )
            # Place conditional orders for SL/TP if provided
            if stop_loss and take_profit:
                sl_params = {
                    'posSide': 'long' if side == 'buy' else 'short',
                    'tdMode': 'cross',
                    'stopLoss': {
                        'triggerPrice': stop_loss,
                        'orderType': 'market'
                    },
                    'takeProfit': {
                        'triggerPrice': take_profit,
                        'orderType': 'market'
                    }
                }
                self.exchange.create_order(
                    symbol=self.symbol,
                    type='conditional',
                    side='sell' if side == 'buy' else 'buy',
                    amount=contracts,
                    params=sl_params
                )
            return order
        except Exception as e:
            print(f"Error placing order: {e}")
            return None

    def trade(self, risk_percentage=0.01, atr_sl_mult=1.5, atr_tp_mult=3, trailing_pct=0.01):
        """
        Main trading loop using ATR-based stop loss/take profit.
        A trailing stop update logic placeholder is provided.
        """
        while True:
            try:
                ticker = self.get_market_data()
                if not ticker:
                    time.sleep(60)
                    continue

                balance = self.exchange.fetch_balance()
                available_usdt = balance['USDT']['free']
                atr = calculate_atr(self.exchange, self.symbol)
                if atr is None:
                    time.sleep(60)
                    continue

                current_price = ticker['last']
                # Calculate stop_loss_pct for position sizing based on ATR multiplier
                stop_loss_pct = (atr * atr_sl_mult) / current_price
                position_size = self.calculate_position_size(
                    capital=available_usdt,
                    risk_percentage=risk_percentage,
                    stop_loss_pct=stop_loss_pct
                )

                print(f"\nCurrent {self.symbol} price: {current_price}")
                print(f"Available USDT: {available_usdt}")
                print(f"Position size (in DOGE): {position_size}")
                print(f"ATR: {atr}")

                open_position = self.get_open_position()

                # Determine SL & TP based on trade direction
                if open_position and open_position['side'] == 'long':
                    stop_loss = current_price - (atr * atr_sl_mult)
                    take_profit = current_price + (atr * atr_tp_mult)
                    trailing_stop = current_price - (current_price * trailing_pct)
                elif open_position and open_position['side'] == 'short':
                    stop_loss = current_price + (atr * atr_sl_mult)
                    take_profit = current_price - (atr * atr_tp_mult)
                    trailing_stop = current_price + (current_price * trailing_pct)
                else:
                    # Default values if no open position exists
                    stop_loss = current_price - (atr * atr_sl_mult)
                    take_profit = current_price + (atr * atr_tp_mult)
                    trailing_stop = current_price - (current_price * trailing_pct)

                # Basic entry signals using ticker percentage change:
                if ticker['percentage'] > 1 and (not open_position or open_position['side'] != 'long'):
                    if open_position:
                        self.close_position(open_position)
                    print(f"Opening LONG position at {current_price}")
                    self.place_order('buy', position_size, stop_loss, take_profit)

                elif ticker['percentage'] < -1 and (not open_position or open_position['side'] != 'short'):
                    if open_position:
                        self.close_position(open_position)
                    print(f"Opening SHORT position at {current_price}")
                    self.place_order('sell', position_size, stop_loss, take_profit)

                # --- Trailing Stop Logic Placeholder ---
                # You can update the trailing stop order here based on favorable price moves.
                # For example, if the price moves favorably, adjust the stop_loss to lock in profits.
                # This part requires additional order management with OKX conditional orders.

            except Exception as e:
                print(f"Error in trading loop: {e}")

            time.sleep(60)

if __name__ == "__main__":
    trader = OKXTrader(API_CREDENTIALS)
    print("Starting live trading with Cross Margin Mode on Sandbox...")
    trader.trade()
