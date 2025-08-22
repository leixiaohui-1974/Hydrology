from abc import ABC, abstractmethod
import numpy as np

class BaseRunoffModule(ABC):
    """
    产流模块的抽象基类。
    """
    @abstractmethod
    def run(self, rainfall, pet):
        pass

class SimpleRunoffModule(BaseRunoffModule):
    """
    简单产流模块。
    """
    def __init__(self, S_max, c_loss, **kwargs):
        self.S_max = S_max
        self.c_loss = c_loss
        self.S = 0.0

    def run(self, rainfall, pet):
        actual_et = min(self.S, pet)
        self.S -= actual_et
        effective_rainfall = rainfall
        if self.S < self.S_max:
            runoff_potential = (self.S / self.S_max) * effective_rainfall
            self.S += effective_rainfall - runoff_potential
            if self.S > self.S_max:
                runoff_potential += self.S - self.S_max
                self.S = self.S_max
        else:
            runoff_potential = effective_rainfall
        loss = min(self.S, self.S * self.c_loss)
        self.S -= loss
        return runoff_potential

class SCSCurveNumberModule(BaseRunoffModule):
    """
    SCS曲线数法产流模块。
    """
    def __init__(self, CN, **kwargs):
        if not (0 < CN <= 100):
            raise ValueError("CN值必须在 (0, 100] 范围内。")
        self.CN = CN
        self.S = 25.4 * (1000 / self.CN - 10)
        self.Ia = 0.2 * self.S

    def run(self, rainfall, pet=0):
        P = rainfall
        if P <= self.Ia:
            return 0.0
        else:
            Q = ((P - self.Ia)**2) / (P - self.Ia + self.S)
            return Q

class XinanjiangRunoffModule(BaseRunoffModule):
    """
    新安江模型的产流模块。
    改编自 https://github.com/OuyangWenyu/hydromodel
    """
    def __init__(self, K, B, IM, UM, LM, DM, C, SM, EX, KI, KG, **kwargs):
        # Parameters
        self.K = K
        self.B = B
        self.IM = IM
        self.UM = UM
        self.LM = LM
        self.DM = DM
        self.C = C
        self.SM = SM
        self.EX = EX
        self.KI = KI
        self.KG = KG

        # State Variables
        self.wu = 0.6 * self.UM
        self.wl = 0.6 * self.LM
        self.wd = 0.6 * self.DM
        self.s = 0.5 * self.SM
        self.fr = 0.1

    def run(self, rainfall, pet):
        # Ensure inputs are non-negative
        prcp = max(rainfall, 0.0)
        pet_in = max(pet, 0.0)

        # 1. Evapotranspiration Calculation
        pet_ = self.K * pet_in
        eu = pet_ if self.wu + prcp >= pet_ else self.wu + prcp

        el = 0.0
        if self.wu + prcp < pet_:
            if self.wl >= self.C * self.LM:
                el = (pet_ - eu) * (self.wl / self.LM)
            else:
                el = (pet_ - eu) * (self.wl / (self.C * self.LM)) if self.C * self.LM > 0 else 0

        ed = 0.0
        if self.C * self.LM > self.wl and self.C * (pet_ - eu) > self.wl:
             ed = self.C * (pet_ - eu) - self.wl

        e_total = eu + el + ed
        pe_net = prcp - e_total

        # 2. Runoff Generation at a point
        w0 = self.wu + self.wl + self.wd
        wm = self.UM + self.LM + self.DM
        w0 = min(w0, wm - 1e-5) # Ensure w0 is not greater than wm

        r = 0.0
        if pe_net > 0:
            wmm = wm * (1 + self.B)
            a = wmm * (1 - (1 - w0 / wm) ** (1 / (1 + self.B)))
            if pe_net + a < wmm:
                r = pe_net - (wm - w0) + wm * (1 - (pe_net + a) / wmm) ** (1 + self.B)
            else:
                r = pe_net - (wm - w0)
        r = max(r, 0.0)

        # Impervious area runoff
        r_im = pe_net * self.IM if pe_net > 0 else 0.0

        # 3. Water Balance - Update Soil Moisture
        wu_old, wl_old, wd_old = self.wu, self.wl, self.wd

        if pe_net >= 0:
            self.wu = min(wu_old + pe_net - r, self.UM)
        else: # pe_net is negative (net evaporation)
            self.wu = wu_old + pe_net

        if pe_net >= 0:
            if (wu_old + wl_old + pe_net - r) > (self.UM + self.LM):
                self.wd = wd_old + (wu_old + wl_old + pe_net - r) - (self.UM + self.LM) - self.wu
            # else wd is unchanged
        else:
            self.wd = wd_old - ed

        if pe_net >= 0:
            self.wl = (wu_old + wl_old + wd_old + pe_net - r) - self.wu - self.wd
        else:
            self.wl = wl_old - el

        self.wu = np.clip(self.wu, 0, self.UM)
        self.wl = np.clip(self.wl, 0, self.LM)
        self.wd = np.clip(self.wd, 0, self.DM)

        # 4. Runoff Separation (Sources)
        pe_for_sources = max(pe_net, 0.0)

        if pe_for_sources > 1e-5:
            current_fr = r / pe_for_sources
            ss = self.s * (self.fr / current_fr) if current_fr > 1e-5 else self.s
        else:
            current_fr = 0
            ss = self.s

        ss = min(ss, self.SM)
        ms = self.SM * (1 + self.EX)

        rs = 0.0
        if pe_for_sources > 0:
            au = ms * (1 - (1 - ss / self.SM) ** (1 / (1 + self.EX)))
            if pe_for_sources + au < ms:
                rs_cal = current_fr * (pe_for_sources - self.SM + ss + self.SM * ((1 - (pe_for_sources + au) / ms) ** (1 + self.EX)))
            else:
                rs_cal = current_fr * (pe_for_sources + ss - self.SM)
            rs = min(max(rs_cal, 0.0), r)

        if current_fr > 1e-5:
            self.s = ss + (r - rs) / current_fr
        # s is updated even if pe is zero, due to outflow

        self.fr = current_fr

        ri = self.KI * self.s * self.fr
        rg = self.KG * self.s * self.fr

        self.s -= (ri + rg) / self.fr if self.fr > 1e-5 else 0
        self.s = np.clip(self.s, 0, self.SM)

        total_runoff = rs * (1 - self.IM) + ri * (1 - self.IM) + rg * (1 - self.IM) + r_im
        return total_runoff

class HymodRunoffModule(BaseRunoffModule):
    """
    HYMOD rainfall-runoff model.
    Adapted from https://github.com/OuyangWenyu/hydromodel
    This module includes both runoff generation and routing.
    """
    def __init__(self, cmax, bexp, alpha, ks, kq, **kwargs):
        # Parameters
        self.cmax = cmax
        self.bexp = bexp
        self.alpha = alpha
        self.ks = ks
        self.kq = kq

        # State Variables
        self.x_loss = 0.0
        self.x_slow = 0.0
        self.x_quick = np.zeros(3)

    def _power(self, x, y):
        # A numba-safe power function
        return np.abs(x) ** y

    def _linres(self, x_in, inflow, k):
        # Linear reservoir routing for one step
        x_out = (1 - k) * x_in + (1 - k) * inflow
        outflow = (k / (1 - k)) * x_out if (1 - k) > 1e-9 else x_out * 1e9
        return x_out, outflow

    def _excess(self, pval, pet_val):
        # Calculates excess precipitation and evaporation
        xn_prev = self.x_loss
        ct_prev = self.cmax * (1 - self._power((1 - ((self.bexp + 1) * xn_prev / self.cmax)), (1 / (self.bexp + 1))))

        # Calculate Effective rainfall 1
        er1 = max(pval - self.cmax + ct_prev, 0.0)
        pval = pval - er1
        dummy = min(((ct_prev + pval) / self.cmax), 1)
        xn = (self.cmax / (self.bexp + 1)) * (1 - self._power((1 - dummy), (self.bexp + 1)))

        # Calculate Effective rainfall 2
        er2 = max(pval - (xn - xn_prev), 0.0)

        # Evaporation
        evap = (1 - (((self.cmax / (self.bexp + 1)) - xn) / (self.cmax / (self.bexp + 1)))) * pet_val
        self.x_loss = max(xn - evap, 0.0)

        return er1, er2

    def run(self, rainfall, pet):
        pval = max(rainfall, 0.0)
        pet_val = max(pet, 0.0)
        er1, er2 = self._excess(pval, pet_val)
        et = er1 + er2
        uq = self.alpha * et
        us = (1 - self.alpha) * et
        self.x_slow, qs = self._linres(self.x_slow, us, self.ks)
        inflow = uq
        for i in range(3):
            self.x_quick[i], outflow = self._linres(self.x_quick[i], inflow, self.kq)
            inflow = outflow
        total_flow = qs + outflow
        return total_flow


class BaseSnowmeltModule(ABC):
    """Abstract base class for snowmelt modules."""
    @abstractmethod
    def run(self, precipitation, temperature):
        """
        Calculates snow accumulation and melt.
        Returns the amount of liquid water available for runoff.
        """
        pass


class SnowmeltRunoffModule(BaseSnowmeltModule):
    """
    A simple Temperature-Index (Degree-Day) snowmelt model.
    This module determines the form of precipitation (rain or snow) and
    calculates snowmelt, outputting the total liquid water available for runoff.
    """
    def __init__(self, degree_day_factor: float, base_temperature: float = 0.0, **kwargs):
        if degree_day_factor < 0:
            raise ValueError("Degree-day factor cannot be negative.")
        self.ddf = degree_day_factor  # Degree-day factor (mm/day/°C)
        self.base_temp = base_temperature # Base temperature for melt (°C)

        # State variable
        self.swe = 0.0  # Snow Water Equivalent (mm)

        # History for plotting/analysis
        self.swe_history = []
        self.melt_history = []

    def get_results(self):
        """Returns the stored history of snowpack and melt."""
        return {
            "SWE": self.swe_history,
            "Melt": self.melt_history
        }

    def run(self, precipitation: float, temperature: float) -> float:
        """
        Runs the snow model for one time step.

        Args:
            precipitation (float): Total precipitation for the timestep (mm).
            temperature (float): Average temperature for the timestep (°C).

        Returns:
            float: The total liquid water available for runoff (rain + snowmelt) in mm.
        """
        rain = 0.0
        snow = 0.0

        # 1. Partition precipitation into rain or snow
        if temperature < self.base_temp:
            snow = precipitation
        else:
            rain = precipitation

        # 2. Add new snow to the snowpack
        self.swe += snow

        # 3. Calculate potential snowmelt
        melt = 0.0
        if self.swe > 0 and temperature > self.base_temp:
            potential_melt = self.ddf * (temperature - self.base_temp)
            # Melt cannot exceed the available snowpack
            melt = min(potential_melt, self.swe)

            # 4. Update snowpack
            self.swe -= melt

        # 5. Total liquid water is rain plus melt
        liquid_water = rain + melt

        # 6. Store history
        self.swe_history.append(self.swe)
        self.melt_history.append(melt)

        return liquid_water
