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
