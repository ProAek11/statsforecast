# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/models.ipynb (unless otherwise specified).

__all__ = ['AutoARIMA', 'ETS', 'SimpleExponentialSmoothing', 'SimpleExponentialSmoothingOptimized',
           'SeasonalExponentialSmoothing', 'SeasonalExponentialSmoothingOptimized', 'HistoricAverage', 'Naive',
           'RandomWalkWithDrift', 'SeasonalNaive', 'WindowAverage', 'SeasonalWindowAverage', 'ADIDA', 'CrostonClassic',
           'CrostonOptimized', 'CrostonSBA', 'IMAPA', 'TSB']

# Cell
from itertools import count
from numbers import Number
from typing import Collection, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from numba import njit
from scipy.optimize import minimize

from .arima import auto_arima_f, forecast_arima, fitted_arima
from .ets import ets_f, forecast_ets

# Cell
class _TS:

    def new(self):
        b = type(self).__new__(type(self))
        b.__dict__.update(self.__dict__)
        return b

# Cell
class AutoARIMA(_TS):

    def __init__(self, season_length: int = 1, approximation: bool = False):
        self.season_length = season_length
        self.approximation = approximation

    def __repr__(self):
        return f'AutoARIMA()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        with np.errstate(invalid='ignore'):
            self.fitted_ = auto_arima_f(
                y,
                xreg=X,
                period=self.season_length,
                approximation=self.approximation,
                allowmean=False, allowdrift=False #not implemented yet
            )
        return self

    def predict(self, h: int, X: np.ndarray = None, level: Optional[Tuple[int]] = None):
        fcst = forecast_arima(self.fitted_, h=h, xreg=X, level=level)
        if level is None:
            return fcst['mean']
        out = [
            fcst['mean'],
            *[fcst['lower'][f'{l}%'] for l in level],
            *[fcst['upper'][f'{l}%'] for l in level],
        ]
        return np.vstack(out).T

    def predict_in_sample(self):
        return fitted_arima(self.fitted_)

# Cell
class ETS(_TS):

    def __init__(self, season_length: int = 1, model: str = 'ZZZ'):
        self.season_length = season_length
        self.model = model

    def __repr__(self):
        return f'ETS(sl={self.season_length},model={self.model})'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = ets_f(y, m=self.season_length, model=self.model)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return forecast_ets(self.fitted_, h=h)['mean']

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Cell
@njit
def _ses_fcst_mse(x: np.ndarray, alpha: float) -> Tuple[float, float]:
    """Perform simple exponential smoothing on a series.

    This function returns the one step ahead prediction
    as well as the mean squared error of the fit.
    """
    smoothed = x[0]
    n = x.size
    mse = 0.
    fitted = np.full(n, np.nan, np.float32)

    for i in range(1, n):
        smoothed = (alpha * x[i - 1] + (1 - alpha) * smoothed).item()
        error = x[i] - smoothed
        mse += error * error
        fitted[i] = smoothed

    mse /= n
    forecast = alpha * x[-1] + (1 - alpha) * smoothed
    return forecast, mse, fitted


def _ses_mse(alpha: float, x: np.ndarray) -> float:
    """Compute the mean squared error of a simple exponential smoothing fit."""
    _, mse, _ = _ses_fcst_mse(x, alpha)
    return mse


@njit
def _ses_forecast(x: np.ndarray, alpha: float) -> float:
    """One step ahead forecast with simple exponential smoothing."""
    forecast, _, fitted = _ses_fcst_mse(x, alpha)
    return forecast, fitted


@njit
def _demand(x: np.ndarray) -> np.ndarray:
    """Extract the positive elements of a vector."""
    return x[x > 0]


@njit
def _intervals(x: np.ndarray) -> np.ndarray:
    """Compute the intervals between non zero elements of a vector."""
    y = []

    ctr = 1
    for val in x:
        if val == 0:
            ctr += 1
        else:
            y.append(ctr)
            ctr = 1

    y = np.array(y)
    return y


@njit
def _probability(x: np.ndarray) -> np.ndarray:
    """Compute the element probabilities of being non zero."""
    return (x != 0).astype(np.int32)


def _optimized_ses_forecast(
        x: np.ndarray,
        bounds: Sequence[Tuple[float, float]] = [(0.1, 0.3)]
    ) -> float:
    """Searches for the optimal alpha and computes SES one step forecast."""
    alpha = minimize(
        fun=_ses_mse,
        x0=(0,),
        args=(x,),
        bounds=bounds,
        method='L-BFGS-B'
    ).x[0]
    forecast, fitted = _ses_forecast(x, alpha)
    return forecast, fitted


@njit
def _chunk_sums(array: np.ndarray, chunk_size: int) -> np.ndarray:
    """Splits an array into chunks and returns the sum of each chunk."""
    n = array.size
    n_chunks = n // chunk_size
    sums = np.empty(n_chunks)
    for i, start in enumerate(range(0, n, chunk_size)):
        sums[i] = array[start : start + chunk_size].sum()
    return sums

# Internal Cell
@njit
def _ses(y: np.ndarray, alpha: float):
    mean, _, fitted_vals = _ses_fcst_mse(y, alpha)
    obj = {'mean': np.array([np.float32(mean)])}
    obj['fitted'] = fitted_vals
    return obj

@njit
def _predict_ses(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class SimpleExponentialSmoothing(_TS):

    def __init__(self, alpha: float):
        self.alpha = alpha

    def __repr__(self):
        return f'SES(alpha={self.alpha})'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _ses(y=y, alpha=self.alpha)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_ses(self.fitted_, h=h)

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Cell
def _ses_optimized(y: np.ndarray):
    mean, fitted_vals = _optimized_ses_forecast(y, [(0.01, 0.99)])
    obj = {'mean': np.array([np.float32(mean)])}
    obj['fitted'] = fitted_vals
    return obj

def _predict_ses_optimized(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class SimpleExponentialSmoothingOptimized(_TS):

    def __init__(self):
        pass

    def __repr__(self):
        return f'SESOpt()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _ses_optimized(y=y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_ses_optimized(self.fitted_, h=h)

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Internal Cell
@njit
def _seasonal_exponential_smoothing(y: np.ndarray, season_length: int, alpha: float):
    if y.size < season_length:
        season_vals = np.full(season_length, np.nan, np.float32)
        fitted = np.full(y.size, np.nan, np.float32)
        return {'season_vals': season_vals, 'fitted': fitted}
    season_vals = np.empty(season_length, np.float32)
    fitted = np.full(y.size, np.nan, np.float32)
    for i in range(season_length):
        season_vals[i], fitted[i::season_length] = _ses_forecast(y[i::season_length], alpha)
    return {'season_vals': season_vals, 'fitted': fitted}

@njit
def _predict_seasonal_es(obj, season_length: int, h: int):
    fcst = np.empty(h, np.float32)
    for i in range(h):
        fcst[i] = obj['season_vals'][i % season_length]
    return fcst

# Cell
class SeasonalExponentialSmoothing(_TS):

    def __init__(self, season_length: int, alpha: float):
        self.season_length = season_length
        self.alpha = alpha

    def __repr__(self):
        return f'SeasonalES(sl={self.season_length},alpha={self.alpha})'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _seasonal_exponential_smoothing(y=y, season_length=self.season_length, alpha=self.alpha)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_seasonal_es(self.fitted_, season_length=self.season_length, h=h)

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Cell
def _seasonal_ses_optimized(y: np.ndarray, season_length: int):
    if y.size < season_length:
        season_vals = np.full(season_length, np.nan, np.float32)
        fitted = np.full(y.size, np.nan, np.float32)
        return {'season_vals': season_vals, 'fitted': fitted}
    season_vals = np.empty(season_length, np.float32)
    fitted = np.full(y.size, np.nan, np.float32)
    for i in range(season_length):
        season_vals[i], fitted[i::season_length] = _optimized_ses_forecast(y[i::season_length], [(0.01, 0.99)])
    return {'season_vals': season_vals, 'fitted': fitted}

def _predict_seasonal_es_opt(obj, season_length: int, h: int):
    fcst = np.empty(h, np.float32)
    for i in range(h):
        fcst[i] = obj['season_vals'][i % season_length]
    return fcst

# Cell
class SeasonalExponentialSmoothingOptimized(_TS):

    def __init__(self, season_length: int):
        self.season_length = season_length

    def __repr__(self):
        return f'SeasESOpt(sl={self.season_length})'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _seasonal_ses_optimized(y=y, season_length=self.season_length)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_seasonal_es_opt(self.fitted_, season_length=self.season_length, h=h)

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Internal Cell
@njit
def _historic_average(y: np.ndarray):
    obj = {'mean': np.array([y.mean()], dtype=np.float32)}
    fitted_vals = np.full(y.size, np.nan, dtype=np.float32)
    fitted_vals[1:] = y.cumsum()[:-1] / np.arange(1, y.size)
    obj['fitted'] = fitted_vals
    return obj

@njit
def _predict_historic_average(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class HistoricAverage(_TS):

    def __init__(self):
        pass

    def __repr__(self):
        return f'HistoricAverage()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _historic_average(y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_historic_average(self.fitted_, h=h)

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Internal Cell
@njit
def _naive(y: np.ndarray):
    obj = {'mean': np.array([y[-1]]).astype(np.float32)}
    fitted_vals = np.full(y.size, np.nan, np.float32)
    fitted_vals[1:] = np.roll(y, 1)[1:]
    obj['fitted'] = fitted_vals
    return obj

@njit
def _predict_naive(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class Naive(_TS):

    def __init__(self):
        pass

    def __repr__(self):
        return f'Naive()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _naive(y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_naive(self.fitted_, h=h)

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Internal Cell
@njit
def _random_walk_with_drift(y: np.ndarray):
    slope = (y[-1] - y[0]) / (y.size - 1)
    slope = np.array([slope]).astype(np.float32)
    mean = np.array([y[-1]]).astype(np.float32)
    obj = {'mean': mean, 'slope': slope}
    fitted_vals = np.full(y.size, np.nan, dtype=np.float32)
    fitted_vals[1:] = (slope + y[:-1]).astype(np.float32)
    obj['fitted'] = fitted_vals
    return obj

@njit
def _predict_rwd(obj, h: int):
    return obj['mean'] + obj['slope'] * (1 + np.arange(h))

# Cell
class RandomWalkWithDrift(_TS):

    def __init__(self):
        pass

    def __repr__(self):
        return f'RWD()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _random_walk_with_drift(y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_rwd(self.fitted_, h=h)

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Internal Cell
@njit
def _seasonal_naive(y: np.ndarray, season_length: int):
    if y.size < season_length:
        season_vals = np.full(season_length, np.nan, np.float32)
        fitted = np.full(y.size, np.nan, np.float32)
        return {'season_vals': season_vals, 'fitted': fitted}
    season_vals = np.empty(season_length, np.float32)
    fitted = np.full(y.size, np.nan, np.float32)
    for i in range(season_length):
        s_naive = _naive(y[i::season_length])
        season_vals[i] = s_naive['mean'].item()
        fitted[i::season_length] = s_naive['fitted']
    return {'season_vals': season_vals, 'fitted': fitted}

@njit
def _predict_seasonal_naive(obj, season_length: int, h: int):
    fcst = np.empty(h, np.float32)
    for i in range(h):
        fcst[i] = obj['season_vals'][i % season_length]
    return fcst

# Cell
class SeasonalNaive(_TS):

    def __init__(self, season_length: int):
        self.season_length = season_length

    def __repr__(self):
        return f'SeasonalNaive(sl={self.season_length})'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _seasonal_naive(y=y, season_length=self.season_length)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_seasonal_naive(self.fitted_, season_length=self.season_length, h=h)

    def predict_in_sample(self):
        return self.fitted_['fitted']

# Internal Cell
@njit
def _window_average(y: np.ndarray, window_size: int):
    if y.size < window_size:
        return {'mean': np.array([np.nan], dtype=np.float32)}
    wavg = y[-window_size:].mean()
    return {'mean': np.array([wavg], dtype=np.float32)}

def _predict_window_average(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class WindowAverage(_TS):

    def __init__(self, window_size: int):
        self.window_size = window_size

    def __repr__(self):
        return f'WindowAverage(ws={self.window_size})'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _window_average(y=y, window_size=self.window_size)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_window_average(self.fitted_, h=h)

    def predict_in_sample(self):
        raise NotImplementedError

# Internal Cell
@njit
def _seasonal_window_average(y: np.ndarray, season_length: int, window_size: int):
    min_samples = season_length * window_size
    if y.size < min_samples:
        return {'seas_avgs': np.full(season_length, fill_value=np.nan, dtype=np.float32)}
    season_avgs = np.zeros(season_length, np.float32)
    for i, value in enumerate(y[-min_samples:]):
        season = i % season_length
        season_avgs[season] += value / window_size
    return {'season_avgs': season_avgs}

@njit
def _predict_seas_wa(obj, season_length: int, h: int):
    fcst = np.empty(h, np.float32)
    for i in range(h):
        fcst[i] = obj['season_avgs'][i % season_length]
    return fcst

# Cell
class SeasonalWindowAverage(_TS):

    def __init__(self, season_length: int, window_size: int):
        self.season_length = season_length
        self.window_size = window_size

    def __repr__(self):
        return f'SeasWA(sl={self.season_length},ws={self.window_size})'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _seasonal_window_average(y=y, season_length=self.season_length, window_size=self.window_size)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_seas_wa(self.fitted_, season_length=self.season_length, h=h)

    def predict_in_sample(self):
        raise NotImplementedError

# Internal Cell
def _adida(y: np.ndarray):
    if (y == 0).all():
        return {'mean': np.array([np.float32(0)])}
    y_intervals = _intervals(y)
    mean_interval = y_intervals.mean()
    aggregation_level = round(mean_interval)
    lost_remainder_data = len(y) % aggregation_level
    y_cut = y[lost_remainder_data:]
    aggregation_sums = _chunk_sums(y_cut, aggregation_level)
    sums_forecast, _ = _optimized_ses_forecast(aggregation_sums)
    forecast = sums_forecast / aggregation_level
    return {'mean': np.array([np.float32(forecast)])}

def _predict_adida(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class ADIDA(_TS):

    def __init__(self):
        pass

    def __repr__(self):
        return f'ADIDA()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _adida(y=y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_adida(self.fitted_, h=h)

    def predict_in_sample(self):
        raise NotImplementedError

# Internal Cell
@njit
def _croston_classic(y: np.ndarray):
    yd = _demand(y)
    yi = _intervals(y)
    ydp, _ = _ses_forecast(yd, 0.1)
    yip, _ = _ses_forecast(yi, 0.1)
    mean = ydp / yip
    return {'mean': np.array([np.float32(mean)])}

@njit
def _predict_croston_classic(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class CrostonClassic(_TS):

    def __init__(self):
        pass

    def __repr__(self):
        return f'CrostonClassic()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _croston_classic(y=y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_croston_classic(self.fitted_, h=h)

    def predict_in_sample(self):
        raise NotImplementedError

# Internal Cell
def _croston_optimized(y: np.ndarray):
    yd = _demand(y)
    yi = _intervals(y)
    ydp, _ = _optimized_ses_forecast(yd)
    yip, _ = _optimized_ses_forecast(yi)
    mean = ydp / yip
    return {'mean': np.array([np.float32(mean)])}

def _predict_croston_optimized(obj, h: int):
     return np.repeat(obj['mean'], h)

# Cell
class CrostonOptimized(_TS):

    def __init__(self):
        pass

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _croston_optimized(y=y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_croston_optimized(self.fitted_, h=h)

    def predict_in_sample(self):
        raise NotImplementedError

# Internal Cell
@njit
def _croston_sba(y: np.ndarray):
    mean = _croston_classic(y)
    mean['mean'] *= 0.95
    return mean

@njit
def _predict_croston_sba(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class CrostonSBA(_TS):

    def __init__(self):
        pass

    def __repr__(self):
        return f'CrostonSBA()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _croston_sba(y=y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_croston_sba(self.fitted_, h=h)

    def predict_in_sample(self):
        raise NotImplementedError

# Internal Cell
def _imapa(y: np.ndarray):
    if (y == 0).all():
        return {'mean': np.array([np.float32(0)])}
    y_intervals = _intervals(y)
    mean_interval = y_intervals.mean().item()
    max_aggregation_level = round(mean_interval)
    forecasts = np.empty(max_aggregation_level, np.float32)
    for aggregation_level in range(1, max_aggregation_level + 1):
        lost_remainder_data = len(y) % aggregation_level
        y_cut = y[lost_remainder_data:]
        aggregation_sums = _chunk_sums(y_cut, aggregation_level)
        forecast, _ = _optimized_ses_forecast(aggregation_sums)
        forecasts[aggregation_level - 1] = (forecast / aggregation_level)
    forecast = forecasts.mean()
    return {'mean': np.array([np.float32(forecast)])}

def _predict_imapa(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class IMAPA(_TS):

    def __init__(self):
        pass

    def __repr__(self):
        return f'IMAPA()'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _imapa(y=y)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_imapa(self.fitted_, h=h)

    def predict_in_sample(self):
        raise NotImplementedError

# Internal Cell
@njit
def _tsb(y: np.ndarray, alpha_d: float, alpha_p: float):
    if (y == 0).all():
        return {'mean': np.array([np.float32(0)])}
    yd = _demand(y)
    yp = _probability(y)
    ypf, _ = _ses_forecast(yp, alpha_p)
    ydf, _ = _ses_forecast(yd, alpha_d)
    forecast = np.float32(ypf * ydf)
    return {'mean': np.array([np.float32(forecast)])}

@njit
def _predict_tsb(obj, h: int):
    return np.repeat(obj['mean'], h)

# Cell
class TSB(_TS):

    def __init__(self, alpha_d: float, alpha_p: float):
        self.alpha_d = alpha_d
        self.alpha_p = alpha_p

    def __repr__(self):
        return f'TSB(d={self.alpha_d},p={self.alpha_p})'

    def fit(self, y: np.ndarray, X: np.ndarray = None):
        self.fitted_ = _tsb(y=y, alpha_d=self.alpha_d, alpha_p=self.alpha_p)
        return self

    def predict(self, h: int, X: np.ndarray = None):
        return _predict_tsb(self.fitted_, h=h)

    def predict_in_sample(self):
        raise NotImplementedError