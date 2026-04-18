"""Horton 下渗模型 — 从大渡河水文项目提取并重构。

基于石耀（shi yao）的原始实现，向量化 NumPy 版本。
物理方程：
  f(t) = f∞ + (f₀ - f∞) * exp(-kd * t)
  其中 f₀ = 干燥状态最大下渗率, f∞ = 饱和最小下渗率
  kd = 下渗衰减系数, kr = 下渗恢复系数
  累积下渗量达到 max_volume 后停止下渗

应用场景：
  1. 独立 Horton 下渗计算（替代 Pipedream 的 Green-Ampt）
  2. 大渡河流域划分后各集水区的产流计算
  3. Hydrology 项目中的下渗模块扩展

Bridge: 大渡河 product.py 提取核心逻辑，Opus 重构为独立模块。
"""

from __future__ import annotations

import numpy as np
from numpy import ndarray


class HortonInfiltration:
    """Horton 下渗模型（向量化，支持网格计算）。

    参数全部可以是标量或与网格等形状的 ndarray。
    """

    def __init__(
        self,
        f0: float | ndarray,
        f_inf: float | ndarray,
        kd: float | ndarray,
        kr: float | ndarray,
        max_volume: float | ndarray = 0.0,
    ) -> None:
        """初始化 Horton 下渗参数。

        Args:
            f0: 干燥状态下最大下渗率 [m/s]
            f_inf: 饱和状态下最小下渗率 [m/s]
            kd: 下渗衰减系数 [1/s]
            kr: 下渗恢复系数 [1/s]
            max_volume: 最大累积下渗量 [m]，0 表示无限
        """
        self.f0 = np.asarray(f0, dtype=float)
        self.f_inf = np.asarray(f_inf, dtype=float)
        self.kd = np.asarray(kd, dtype=float)
        self.kr = np.asarray(kr, dtype=float)
        self.max_volume = np.asarray(max_volume, dtype=float)

        # 状态变量
        shape = np.broadcast_shapes(
            self.f0.shape, self.f_inf.shape,
            self.kd.shape, self.kr.shape,
        )
        self.fp = np.broadcast_to(self.f0, shape).copy()  # 当前下渗能力
        self.Fp = np.zeros(shape, dtype=float)  # 累积下渗量

    def reset(self) -> None:
        """重置下渗状态到初始干燥条件。"""
        shape = self.fp.shape
        self.fp = np.broadcast_to(self.f0, shape).copy()
        self.Fp = np.zeros(shape, dtype=float)

    def step(self, rainfall: float | ndarray, dt: float) -> dict[str, ndarray]:
        """执行一个时间步的下渗计算。

        Args:
            rainfall: 降雨量 [m]（本时间步内的总降雨深度）
            dt: 时间步长 [s]

        Returns:
            dict 包含：
              infiltration: 实际下渗量 [m]
              runoff: 产流量 [m]（= rainfall - infiltration）
              fp: 更新后的下渗能力 [m/s]
              Fp: 更新后的累积下渗量 [m]
        """
        f_real, fp_next, Fp_next = self._horton_step(
            self.fp, rainfall, self.Fp, dt,
            self.f0, self.f_inf, self.kd, self.kr, self.max_volume,
        )
        self.fp = fp_next
        self.Fp = Fp_next

        runoff = np.maximum(rainfall - f_real, 0.0)
        return {
            "infiltration": f_real,
            "runoff": runoff,
            "fp": fp_next,
            "Fp": Fp_next,
        }

    def _horton_step(
        self, fp: ndarray, rp: ndarray, Fp: ndarray, dt: float,
        f0: ndarray, f_inf: ndarray, kd: ndarray, kr: ndarray,
        max_volume: ndarray,
    ) -> tuple[ndarray, ndarray, ndarray]:
        """Horton 下渗单步计算（向量化）。"""
        fp, rp, Fp, f0, f_inf, kd, kr, max_volume = np.broadcast_arrays(
            np.asarray(fp), np.asarray(rp), np.asarray(Fp),
            np.asarray(f0), np.asarray(f_inf), np.asarray(kd),
            np.asarray(kr), np.asarray(max_volume),
        )
        shape = fp.shape

        f_real = np.zeros(shape, dtype=float)
        f_next = np.zeros(shape, dtype=float)
        F_next = np.zeros(shape, dtype=float)

        maxv = np.where(max_volume == 0, 1e6, max_volume)

        m_rp_pos = rp > 0
        m_rp_neg = ~m_rp_pos

        # 有降雨/积水情况
        if np.any(m_rp_pos):
            m_f0_zero = m_rp_pos & (f0 == 0)
            m_run = m_rp_pos & (f0 != 0)

            if np.any(m_f0_zero):
                f_real[m_f0_zero] = 0.0
                F_next[m_f0_zero] = 0.0
                f_next[m_f0_zero] = 0.0

            if np.any(m_run):
                m_below = m_run & (Fp < maxv)
                if np.any(m_below):
                    f_tmp = np.minimum(fp * dt, rp)
                    F_tmp = Fp + f_tmp
                    m_over = m_below & (F_tmp > maxv)
                    if np.any(m_over):
                        overflow = F_tmp - maxv
                        f_tmp = np.where(m_over, f_tmp - overflow, f_tmp)
                        F_tmp = np.where(m_over, maxv, Fp + f_tmp)
                    f_real[m_below] = f_tmp[m_below]
                    F_next[m_below] = F_tmp[m_below]

                m_above = m_run & ~(Fp < maxv)
                if np.any(m_above):
                    f_real[m_above] = 0.0
                    F_next[m_above] = maxv[m_above]

                # 更新下渗能力: 求解 t - b*exp(c*t) - a = 0
                a = (kd[m_run] * F_next[m_run] - f0[m_run] + f_inf[m_run]) / (kd[m_run] * f_inf[m_run])
                b = (f0[m_run] - f_inf[m_run]) / (kd[m_run] * f_inf[m_run])
                c = -kd[m_run]
                t_sol = _newton_raphson(a, b, c)
                f_next[m_run] = f_inf[m_run] + (f0[m_run] - f_inf[m_run]) * np.exp(-kd[m_run] * t_sol)

        # 无降雨：下渗能力恢复
        if np.any(m_rp_neg):
            m_fp_pos = m_rp_neg & (Fp > 0)
            if np.any(m_fp_pos):
                f_next[m_fp_pos] = (
                    f0[m_fp_pos]
                    - (f0[m_fp_pos] - fp[m_fp_pos]) * np.exp(-kr[m_fp_pos] * dt)
                )
                # 恢复后的累积下渗量
                ratio = np.clip(
                    (f_next[m_fp_pos] - f_inf[m_fp_pos])
                    / np.maximum(f0[m_fp_pos] - f_inf[m_fp_pos], 1e-30),
                    1e-30, 1.0,
                )
                F_next[m_fp_pos] = (
                    (-f_inf[m_fp_pos] / kd[m_fp_pos]) * np.log(ratio)
                    + (f0[m_fp_pos] - f_next[m_fp_pos]) / kd[m_fp_pos]
                )

            m_fp_neg = m_rp_neg & ~(Fp > 0)
            if np.any(m_fp_neg):
                F_next[m_fp_neg] = 0.0
                f_next[m_fp_neg] = f0[m_fp_neg]

        return f_real, f_next, F_next


def _newton_raphson(
    a: ndarray, b: ndarray, c: ndarray,
    max_iter: int = 50, tol: float = 1e-4,
) -> ndarray:
    """求解方程 t - b * exp(c * t) - a = 0。

    Newton-Raphson 迭代，全向量化。
    """
    t = np.maximum(a, 0.0) + 5e-5
    for _ in range(max_iter):
        f = t - b * np.exp(c * t) - a
        df = 1.0 - b * c * np.exp(c * t)
        df = np.where(np.abs(df) < 1e-30, 1e-30, df)
        t_new = t - f / df
        if np.all(np.abs(f) < tol):
            break
        t = t_new
    return t


def horton_from_landuse(
    landuse_grid: ndarray,
    inf_params: dict[int, dict[str, float]],
    recover_percent: float = 0.98,
) -> HortonInfiltration:
    """根据土地利用类型网格创建 Horton 下渗模型。

    Args:
        landuse_grid: 土地利用类型栅格 (H, W)，整数编码
        inf_params: {土地利用代码: {"f0": mm/h, "foo": mm/h, "kd": 1/h, "kr": d, "max_volume": mm}}
        recover_percent: 下渗恢复百分比（用于计算 kr_s）

    Returns:
        HortonInfiltration 实例
    """
    shape = landuse_grid.shape
    f0 = np.zeros(shape, dtype=float)
    f_inf = np.zeros(shape, dtype=float)
    kd = np.zeros(shape, dtype=float)
    kr = np.zeros(shape, dtype=float)
    max_vol = np.zeros(shape, dtype=float)

    for code, params in inf_params.items():
        mask = landuse_grid == code
        if not np.any(mask):
            continue
        f0[mask] = params.get("f0", 10.0) / 3.6e6  # mm/h → m/s
        f_inf[mask] = params.get("foo", 2.0) / 3.6e6
        kd[mask] = params.get("kd", 4.0) / 3600  # 1/h → 1/s
        kr_day = params.get("kr", 1.0)  # 天
        kr[mask] = -np.log(1 - recover_percent) / (kr_day * 86400)  # → 1/s
        max_vol[mask] = params.get("max_volume", 100.0) / 1000  # mm → m

    return HortonInfiltration(f0=f0, f_inf=f_inf, kd=kd, kr=kr, max_volume=max_vol)
