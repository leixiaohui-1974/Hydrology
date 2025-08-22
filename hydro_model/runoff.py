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
