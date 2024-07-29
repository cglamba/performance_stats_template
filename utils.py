#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import io as io
import datetime as dt
import pandas as pd
import numpy as np
import yfinance as yf
import stats as _stats
import inspect


def _mtd(df):
    return df[df.index >= dt.datetime.now().strftime("%Y-%m-01")]


def _qtd(df):
    date = dt.datetime.now()
    for q in [1, 4, 7, 10]:
        if date.month <= q:
            return df[df.index >= dt.datetime(date.year, q, 1).strftime("%Y-%m-01")]
    return df[df.index >= date.strftime("%Y-%m-01")]


def _ytd(df):
    return df[df.index >= dt.datetime.now().strftime("%Y-01-01")]


def _pandas_date(df, dates):
    if not isinstance(dates, list):
        dates = [dates]
    return df[df.index.isin(dates)]


def _pandas_current_month(df):
    n = dt.datetime.now()
    daterange = pd.date_range(dt.date(n.year, n.month, 1), n)
    return df[df.index.isin(daterange)]


def multi_shift(df, shift=3):
    """Get last N rows relative to another row in pandas"""
    if isinstance(df, pd.Series):
        df = pd.DataFrame(df)

    dfs = [df.shift(i) for i in np.arange(shift)]
    for ix, dfi in enumerate(dfs[1:]):
        dfs[ix + 1].columns = [str(col) for col in dfi.columns + str(ix + 1)]
    return pd.concat(dfs, 1, sort=True)


def to_returns(prices, rf=0.0):
    """Calculates the simple arithmetic returns of a price series"""
    return _prepare_returns(prices, rf)


def to_prices(returns, base=1e5):
    """Converts returns series to price data"""
    returns = returns.copy().fillna(0).replace([np.inf, -np.inf], float("NaN"))

    return base + base * _stats.compsum(returns)


def log_returns(returns, rf=0.0, nperiods=None):
    """Shorthand for to_log_returns"""
    return to_log_returns(returns, rf, nperiods)


def to_log_returns(returns, rf=0.0, nperiods=None):
    """Converts returns series to log returns"""
    returns = _prepare_returns(returns, rf, nperiods)
    try:
        return np.log(returns + 1).replace([np.inf, -np.inf], float("NaN"))
    except Exception:
        return 0.0


def exponential_stdev(returns, window=30, is_halflife=False):
    """Returns series representing exponential volatility of returns"""
    returns = _prepare_returns(returns)
    halflife = window if is_halflife else None
    return returns.ewm(
        com=None, span=window, halflife=halflife, min_periods=window
    ).std()


def rebase(prices, base=100.0):
    """
    Rebase all series to a given intial base.
    This makes comparing/plotting different series together easier.
    Args:
        * prices: Expects a price series/dataframe
        * base (number): starting value for all series.
    """
    return prices.dropna() / prices.dropna().iloc[0] * base


def group_returns(returns, groupby, compounded=False):
    """Summarize returns
    group_returns(df, df.index.year)
    group_returns(df, [df.index.year, df.index.month])
    """
    if compounded:
        return returns.groupby(groupby).apply(_stats.comp)
    return returns.groupby(groupby).sum()


def aggregate_returns(returns, period=None, compounded=True):
    """Aggregates returns based on date periods"""
    if period is None or "day" in period:
        return returns
    index = returns.index

    if "month" in period:
        return group_returns(returns, index.month, compounded=compounded)

    if "quarter" in period:
        return group_returns(returns, index.quarter, compounded=compounded)

    if period == "A" or any(x in period for x in ["year", "eoy", "yoy"]):
        return group_returns(returns, index.year, compounded=compounded)

    if "week" in period:
        return group_returns(returns, index.week, compounded=compounded)

    if "eow" in period or period == "W":
        return group_returns(returns, [index.year, index.week], compounded=compounded)

    if "eom" in period or period == "M":
        return group_returns(returns, [index.year, index.month], compounded=compounded)

    if "eoq" in period or period == "Q":
        return group_returns(
            returns, [index.year, index.quarter], compounded=compounded
        )

    if not isinstance(period, str):
        return group_returns(returns, period, compounded)

    return returns


def to_excess_returns(returns, rf, nperiods=None):
    """
    Calculates excess returns by subtracting
    risk-free returns from total returns

    Args:
        * returns (Series, DataFrame): Returns
        * rf (float, Series, DataFrame): Risk-Free rate(s)
        * nperiods (int): Optional. If provided, will convert rf to different
            frequency using deannualize
    Returns:
        * excess_returns (Series, DataFrame): Returns - rf
    """
    if isinstance(rf, int):
        rf = float(rf)

    if not isinstance(rf, float):
        rf = rf[rf.index.isin(returns.index)]

    if nperiods is not None:
        # deannualize
        rf = np.power(1 + rf, 1.0 / nperiods) - 1.0

    return returns - rf


def _prepare_prices(data, base=1.0):
    """Converts return data into prices + cleanup"""
    data = data.copy()
    if isinstance(data, pd.DataFrame):
        for col in data.columns:
            if data[col].dropna().min() <= 0 or data[col].dropna().max() < 1:
                data[col] = to_prices(data[col], base)

    # is it returns?
    # elif data.min() < 0 and data.max() < 1:
    elif data.min() < 0 or data.max() < 1:
        data = to_prices(data, base)

    if isinstance(data, (pd.DataFrame, pd.Series)):
        data = data.fillna(0).replace([np.inf, -np.inf], float("NaN"))

    return data


def _prepare_returns(data, rf=0.0, nperiods=None):
    """Converts price data into returns + cleanup"""
    data = data.copy()
    function = inspect.stack()[1][3]
    if isinstance(data, pd.DataFrame):
        for col in data.columns:
            if data[col].dropna().min() >= 0 and data[col].dropna().max() > 1:
                data[col] = data[col].pct_change()
    elif data.min() >= 0 and data.max() > 1:
        data = data.pct_change()

    # cleanup data
    data = data.replace([np.inf, -np.inf], float("NaN"))

    if isinstance(data, (pd.DataFrame, pd.Series)):
        data = data.fillna(0).replace([np.inf, -np.inf], float("NaN"))
    unnecessary_function_calls = [
        "_prepare_benchmark",
        "cagr",
        "gain_to_pain_ratio",
        "rolling_volatility",
    ]

    if function not in unnecessary_function_calls:
        if rf > 0:
            return to_excess_returns(data, rf, nperiods)
    return data


def download_returns(ticker, period="max", proxy=None):
    params = {
        "tickers": ticker,
        "proxy": proxy,
    }
    if isinstance(period, pd.DatetimeIndex):
        params["start"] = period[0]
    else:
        params["period"] = period
    return yf.download(**params)["Close"].pct_change()


def _prepare_benchmark(benchmark, returns):
    _name = benchmark.name
    benchmark = returns.to_frame('strategy').join(benchmark.to_frame(_name))[_name]
    benchmark.index = benchmark.index.tz_localize(None)
    return benchmark

def _round_to_closest(val, res, decimals=None):
    """Round to closest resolution"""
    if decimals is None and "." in str(res):
        decimals = len(str(res).split(".")[1])
    return round(round(val / res) * res, decimals)


def _file_stream():
    """Returns a file stream"""
    return io.BytesIO()


def _in_notebook(matplotlib_inline=False):
    """Identify enviroment (notebook, terminal, etc)"""
    try:
        shell = get_ipython().__class__.__name__
        if shell == "ZMQInteractiveShell":
            # Jupyter notebook or qtconsole
            if matplotlib_inline:
                get_ipython().magic("matplotlib inline")
            return True
        if shell == "TerminalInteractiveShell":
            # Terminal running IPython
            return False
        # Other type (?)
        return False
    except NameError:
        # Probably standard Python interpreter
        return False


def _count_consecutive(data):
    """Counts consecutive data (like cumsum() with reset on zeroes)"""

    def _count(data):
        return data * (data.groupby((data != data.shift(1)).cumsum()).cumcount() + 1)

    if isinstance(data, pd.DataFrame):
        for col in data.columns:
            data[col] = _count(data[col])
        return data
    return _count(data)


def _score_str(val):
    """Returns + sign for positive values (used in plots)"""
    return ("" if "-" in val else "+") + str(val)


def make_index(
    ticker_weights, rebalance="1M", period="max", returns=None, match_dates=False
):
    """
    Makes an index out of the given tickers and weights.
    Optionally you can pass a dataframe with the returns.
    If returns is not given it try to download them with yfinance

    Args:
        * ticker_weights (Dict): A python dict with tickers as keys
            and weights as values
        * rebalance: Pandas resample interval or None for never
        * period: time period of the returns to be downloaded
        * returns (Series, DataFrame): Optional. Returns If provided,
            it will fist check if returns for the given ticker are in
            this dataframe, if not it will try to download them with
            yfinance
    Returns:
        * index_returns (Series, DataFrame): Returns for the index
    """
    # Declare a returns variable
    index = None
    portfolio = {}

    # Iterate over weights
    for ticker in ticker_weights.keys():
        if (returns is None) or (ticker not in returns.columns):
            # Download the returns for this ticker, e.g. GOOG
            ticker_returns = download_returns(ticker, period)
        else:
            ticker_returns = returns[ticker]

        portfolio[ticker] = ticker_returns

    # index members time-series
    index = pd.DataFrame(portfolio).dropna()

    if match_dates:
        index = index[max(index.ne(0).idxmax()) :]

    # no rebalance?
    if rebalance is None:
        for ticker, weight in ticker_weights.items():
            index[ticker] = weight * index[ticker]
        return index.sum(axis=1)

    last_day = index.index[-1]

    # rebalance marker
    rbdf = index.resample(rebalance).first()
    rbdf["break"] = rbdf.index.strftime("%s")

    # index returns with rebalance markers
    index = pd.concat([index, rbdf["break"]], axis=1)

    # mark first day day
    index["first_day"] = pd.isna(index["break"]) & ~pd.isna(index["break"].shift(1))
    index.loc[index.index[0], "first_day"] = True

    # multiply first day of each rebalance period by the weight
    for ticker, weight in ticker_weights.items():
        index[ticker] = np.where(
            index["first_day"], weight * index[ticker], index[ticker]
        )

    # drop first marker
    index.drop(columns=["first_day"], inplace=True)

    # drop when all are NaN
    index.dropna(how="all", inplace=True)
    return index[index.index <= last_day].sum(axis=1)


def make_portfolio(returns, start_balance=1e5, mode="comp", round_to=None):
    """Calculates compounded value of portfolio"""
    returns = _prepare_returns(returns)

    if mode.lower() in ["cumsum", "sum"]:
        p1 = start_balance + start_balance * returns.cumsum()
    elif mode.lower() in ["compsum", "comp"]:
        p1 = to_prices(returns, start_balance)
    else:
        # fixed amount every day
        comp_rev = (start_balance + start_balance * returns.shift(1)).fillna(
            start_balance
        ) * returns
        p1 = start_balance + comp_rev.cumsum()

    # add day before with starting balance
    p0 = pd.Series(data=start_balance, index=p1.index + pd.Timedelta(days=-1))[:1]

    portfolio = pd.concat([p0, p1])

    if isinstance(returns, pd.DataFrame):
        portfolio.iloc[:1, :] = start_balance
        portfolio.drop(columns=[0], inplace=True)

    if round_to:
        portfolio = np.round(portfolio, round_to)

    return portfolio


def _flatten_dataframe(df, set_index=None):
    """Dirty method for flattening multi-index dataframe"""
    s_buf = io.StringIO()
    df.to_csv(s_buf)
    s_buf.seek(0)

    df = pd.read_csv(s_buf)
    if set_index is not None:
        df.set_index(set_index, inplace=True)

    return df