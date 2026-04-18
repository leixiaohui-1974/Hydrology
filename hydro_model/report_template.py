# -*- coding: utf-8 -*-
"""通用流域水文报告 HTML 生成器。

输入：流域数据字典，输出：自包含 HTML（GIS地图+图表+文字）。
支持任意流域，不绑定特定案例。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

_EMPTY_FC = '{"type":"FeatureCollection","features":[]}'

_CSS = '*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\nhtml { scroll-behavior: smooth; }\nbody { font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; font-size: 15px; color: #212121; background: #F5F7FA; }\nnav { position: fixed; top: 0; left: 0; width: 220px; height: 100vh; background: #fff; border-right: 1px solid #E0E0E0; box-shadow: 2px 0 8px rgba(0,0,0,.08); z-index: 1000; overflow-y: auto; display: flex; flex-direction: column; }\n.nav-logo { background: linear-gradient(135deg, #1565C0 0%, #1976D2 100%); color: #fff; padding: 20px 16px 14px; font-size: 14px; font-weight: 700; line-height: 1.4; }\n.logo-sub { display: block; font-size: 11px; font-weight: 400; opacity: .8; margin-top: 4px; }\nnav ul { list-style: none; padding: 10px 0; flex: 1; }\nnav ul li a { display: block; padding: 10px 18px; color: #424242; text-decoration: none; font-size: 13px; border-left: 3px solid transparent; transition: all .18s; }\nnav ul li a:hover, nav ul li a.active { background: #E3F2FD; color: #1565C0; border-left-color: #1565C0; }\n.nav-num { display: inline-block; width: 22px; height: 22px; line-height: 22px; text-align: center; background: #1565C0; color: #fff; border-radius: 50%; font-size: 11px; margin-right: 8px; }\nnav ul li a:hover .nav-num, nav ul li a.active .nav-num { background: #42A5F5; }\n.nav-footer { padding: 12px 16px; font-size: 11px; color: #9E9E9E; border-top: 1px solid #EEE; }\nmain { margin-left: 240px; padding: 32px 40px 60px; max-width: 1200px; }\nsection { background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,.07); padding: 32px 36px; margin-bottom: 36px; }\n.section-header { display: flex; align-items: center; gap: 14px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 2px solid #E3F2FD; }\n.snc { width: 42px; height: 42px; background: #1565C0; color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 19px; font-weight: 700; flex-shrink: 0; }\n.section-title { font-size: 22px; font-weight: 700; color: #1565C0; }\n.section-subtitle { font-size: 13px; color: #757575; margin-top: 3px; }\n.h3 { margin: 20px 0 12px; color: #1565C0; font-size: 16px; font-weight: 600; }\n.img-container { margin: 22px 0; text-align: center; }\n.img-container img { max-width: 100%; border-radius: 8px; box-shadow: 0 3px 14px rgba(0,0,0,.12); }\n.img-caption { margin-top: 8px; font-size: 13px; color: #757575; font-style: italic; }\n.img-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }\n.table-wrap { overflow-x: auto; margin: 20px 0; }\ntable { width: 100%; border-collapse: collapse; font-size: 14px; }\nthead th { background: #1565C0; color: #fff; padding: 11px 14px; text-align: left; font-weight: 600; }\ntbody tr:nth-child(even) { background: #F5F7FA; }\ntbody tr:nth-child(odd) { background: #fff; }\ntbody tr:hover { background: #E3F2FD; }\ntbody td { padding: 10px 14px; border-bottom: 1px solid #EEE; color: #424242; }\n.info-box { background: #E3F2FD; border-left: 4px solid #1565C0; border-radius: 0 6px 6px 0; padding: 14px 18px; margin: 16px 0; font-size: 14px; color: #37474F; line-height: 1.8; }\n.info-box strong { color: #1565C0; }\n.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 16px; margin: 20px 0; }\n.mc { background: linear-gradient(135deg, #1565C0 0%, #42A5F5 100%); color: #fff; border-radius: 10px; padding: 18px 14px; text-align: center; }\n.mc.orange { background: linear-gradient(135deg, #E65100 0%, #FF9800 100%); }\n.mc.green { background: linear-gradient(135deg, #2E7D32 0%, #66BB6A 100%); }\n.mc.purple { background: linear-gradient(135deg, #4527A0 0%, #9575CD 100%); }\n.mv { font-size: 24px; font-weight: 700; line-height: 1.2; }\n.ml { font-size: 12px; opacity: .85; margin-top: 4px; }\n#gis-map { height: 600px; border-radius: 8px; box-shadow: 0 3px 14px rgba(0,0,0,.12); margin: 20px 0; }\n.map-legend { background: rgba(255,255,255,.96); padding: 10px 14px; border-radius: 6px; box-shadow: 0 1px 6px rgba(0,0,0,.15); font-size: 12px; line-height: 1.9; }\n.map-legend h4 { font-size: 13px; color: #1565C0; margin-bottom: 6px; font-weight: 700; }\n.li { display: flex; align-items: center; gap: 7px; }\n.lc { width: 14px; height: 14px; border-radius: 3px; border: 1px solid rgba(0,0,0,.15); flex-shrink: 0; }\n.ll { width: 22px; height: 3px; border-radius: 2px; flex-shrink: 0; }\n.conclusion-list { list-style: none; padding: 0; margin: 16px 0; }\n.conclusion-list li { display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; border-bottom: 1px solid #EEE; font-size: 14px; line-height: 1.7; color: #424242; }\n.conclusion-list li:last-child { border-bottom: none; }\n.cn { width: 28px; height: 28px; background: #1565C0; color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex-shrink: 0; margin-top: 2px; }\nfooter { margin-left: 240px; text-align: center; padding: 18px; font-size: 13px; color: #9E9E9E; border-top: 1px solid #E0E0E0; background: #fff; }\n@media (max-width: 768px) { nav { transform: translateX(-220px); transition: transform .3s; } nav.open { transform: translateX(0); } main, footer { margin-left: 0; padding: 14px; } .menu-btn { display: block; position: fixed; top: 10px; left: 10px; z-index: 1100; background: #1565C0; color: #fff; border: none; border-radius: 6px; padding: 7px 11px; font-size: 18px; cursor: pointer; } .img-grid { grid-template-columns: 1fr; } }\n@media (min-width: 769px) { .menu-btn { display: none; } }\n@media print { nav, .menu-btn, footer { display: none !important; } main { margin-left: 0; padding: 0; } section { box-shadow: none; page-break-inside: avoid; } #gis-map { display: none; } }\n'


@dataclass
class WatershedReportData:
    """流域报告数据容器。"""
    name: str = "未命名流域"
    location: str = ""
    area_km2: float = 0.0
    elevation_range: tuple[float, float] = (0.0, 0.0)
    dem_resolution: str = ""
    n_subbasins: int = 0
    n_zones: int = 0
    subbasins_geojson: str = ""
    rivers_geojson: str = ""
    landuse_geojson: str = ""
    soil_geojson: str = ""
    gauging_stations: list[dict] = field(default_factory=list)
    rain_gauges: list[dict] = field(default_factory=list)
    map_center: tuple[float, float] = (0.0, 0.0)
    map_zoom: int = 11
    zone_colors: dict[str, str] = field(default_factory=dict)
    figures: dict[str, str] = field(default_factory=dict)
    zones_table: list[dict] = field(default_factory=list)
    rainfall_stats: dict[str, Any] = field(default_factory=dict)
    simulation_metrics: dict[str, float] = field(default_factory=dict)
    enkf_metrics: dict[str, Any] | None = None
    extra_sections: list[dict] = field(default_factory=list)
    report_date: str = field(default_factory=lambda: date.today().isoformat())

class WatershedReportGenerator:
    """通用流域水文报告 HTML 生成器。

    用法::

        data = WatershedReportData(name="Boulder Creek", ...)
        gen = WatershedReportGenerator()
        gen.generate_file(data, "report.html")
    """

    def generate(self, data: WatershedReportData) -> str:
        """生成完整 HTML 字符串。"""
        sections_html: list[str] = []
        nav_items: list[tuple[str, str]] = []
        sec_num = 1

        def add(anchor: str, label: str, html: str) -> None:
            nonlocal sec_num
            sections_html.append(html)
            nav_items.append((anchor, label))
            sec_num += 1

        add("overview", "流域概况", self._section_overview(data, sec_num))
        add("gis", "GIS 交互地图", self._section_gis_map(data, sec_num))
        if data.figures.get("dem_analysis") or data.figures.get("delineation_debug_plot"):
            add("dem", "DEM 分析", self._section_dem(data, sec_num))
        if data.zones_table or data.figures.get("zones_map") or data.figures.get("parameter_zones_map"):
            add("zones", "参数分区", self._section_zones(data, sec_num))
        if data.rainfall_stats:
            add("rainfall", "面雨量计算", self._section_rainfall(data, sec_num))
        if data.simulation_metrics or data.figures.get("comparison_plot"):
            add("simulation", "水文模拟结果", self._section_simulation(data, sec_num))
        if data.enkf_metrics is not None:
            add("enkf", "EnKF 参数率定", self._section_enkf(data, sec_num))
        for i, extra in enumerate(data.extra_sections):
            add(f"extra_{i}", extra["title"], self._section_extra(extra, f"extra_{i}", sec_num))
        add("conclusion", "结论与展望", self._section_conclusion(data, sec_num))
        return self._wrap_html(data, nav_items, sections_html)

    def generate_file(self, data: WatershedReportData, output_path: str | Path) -> Path:
        """生成 HTML 文件，自动创建父目录。"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.generate(data), encoding="utf-8")
        return path
    def _section_overview(self, data: WatershedReportData, num: int) -> str:
        info_lines = []
        if data.name: info_lines.append(f"<strong>流域名称：</strong>{data.name}")
        if data.location: info_lines.append(f"<strong>地理位置：</strong>{data.location}")
        if data.area_km2: info_lines.append(f"<strong>流域面积：</strong>{data.area_km2:.2f} km²")
        if data.elevation_range and (data.elevation_range[0] or data.elevation_range[1]):
            info_lines.append(f"<strong>高程范围：</strong>{data.elevation_range[0]:.1f} ~ {data.elevation_range[1]:.1f} m")
        if data.dem_resolution: info_lines.append(f"<strong>DEM 分辨率：</strong>{data.dem_resolution}")
        if data.n_subbasins: info_lines.append(f"<strong>子流域数量：</strong>{data.n_subbasins} 个")
        if data.n_zones: info_lines.append(f"<strong>参数分区数：</strong>{data.n_zones} 个")
        info_html = self._info_box("<br>".join(info_lines)) if info_lines else ""
        cards = []
        if data.n_subbasins: cards.append(self._metric_card(str(data.n_subbasins), "子流域数量", ""))
        if data.area_km2: cards.append(self._metric_card(f"{data.area_km2:.1f}", "流域面积 km²", "green"))
        if data.elevation_range and (data.elevation_range[0] or data.elevation_range[1]):
            cards.append(self._metric_card(f"{data.elevation_range[0]:.0f}~{data.elevation_range[1]:.0f} m", "高程范围", "orange"))
        if data.n_zones: cards.append(self._metric_card(str(data.n_zones), "参数分区数", "purple"))
        cards_html = '<div class="metric-grid">' + "".join(cards) + "</div>" if cards else ""
        return self._section_wrap("overview", num, "流域概况", "基本信息与关键指标", info_html + cards_html)

    def _section_gis_map(self, data: WatershedReportData, num: int) -> str:
        n_g, n_r = len(data.gauging_stations), len(data.rain_gauges)
        parts = []
        if data.subbasins_geojson: parts.append("子流域分区（按 zone 着色）")
        if data.rivers_geojson: parts.append("河流（蓝色）")
        if data.landuse_geojson: parts.append("土地利用")
        if data.soil_geojson: parts.append("土壤类型")
        if n_g: parts.append(f"{n_g} 个水文站（红三角）")
        if n_r: parts.append(f"{n_r} 个雨量站（蓝圆）")
        desc = "、".join(parts) if parts else "暂无图层数据"
        info_html = self._info_box(f"地图包含以下可切换图层：<strong>{desc}</strong>")
        map_div = '<div id="gis-map"></div>'
        rows = []
        if data.subbasins_geojson: rows.append(["子流域边界", str(data.n_subbasins) if data.n_subbasins else "—", "按参数分区着色"])
        if data.rivers_geojson: rows.append(["河流", "—", "蓝色实线"])
        if data.landuse_geojson: rows.append(["土地利用", "—", "分类面要素"])
        if data.soil_geojson: rows.append(["土壤类型", "—", "分类面要素"])
        if n_g: rows.append(["水文站", str(n_g), "红三角标记"])
        if n_r: rows.append(["雨量站", str(n_r), "蓝圆标记"])
        table_html = self._table(["图层", "要素数", "说明"], rows) if rows else ""
        return self._section_wrap("gis", num, "流域 GIS 交互地图", "Leaflet.js 多图层交互", info_html + map_div + table_html)

    def _section_dem(self, data: WatershedReportData, num: int) -> str:
        figs = data.figures
        fig_src = figs.get("dem_analysis") or figs.get("delineation_debug_plot", "")
        lines = []
        if data.elevation_range and (data.elevation_range[0] or data.elevation_range[1]):
            lines.append(f"<strong>高程范围：</strong>{data.elevation_range[0]:.1f} ~ {data.elevation_range[1]:.1f} m")
        if data.dem_resolution: lines.append(f"<strong>DEM 分辨率：</strong>{data.dem_resolution}")
        if data.n_subbasins: lines.append(f"<strong>提取子流域数：</strong>{data.n_subbasins} 个")
        if data.area_km2: lines.append(f"<strong>流域总面积：</strong>{data.area_km2:.2f} km²")
        body = (self._info_box("<br>".join(lines)) if lines else "") + (self._img(fig_src, "DEM 水文分析图") if fig_src else "")
        return self._section_wrap("dem", num, "DEM 分析与流域划分", "数字高程模型水文分析", body)
    def _section_zones(self, data: WatershedReportData, num: int) -> str:
        figs = data.figures
        fig_src = figs.get("zones_map") or figs.get("parameter_zones_map") or figs.get("zones", "")
        info_lines = []
        if data.n_zones: info_lines.append(f"<strong>分区总数：</strong>{data.n_zones} 个")
        if data.zone_colors: info_lines.append(f"<strong>分区标识：</strong>{chr(12289).join(data.zone_colors.keys())}")
        info_html = self._info_box("<br>".join(info_lines)) if info_lines else ""
        img_html = self._img(fig_src, "图 — 参数分区地图") if fig_src else ""
        table_html = ""
        if data.zones_table:
            zt = data.zones_table
            if zt and isinstance(zt[0], dict):
                km = {"zone_id": "分区 ID", "n_subbasins": "子流域数", "area_km2": "面积 km²", "pct": "占比 %", "description": "位置特征"}
                rk = list(zt[0].keys())
                headers = [km.get(k, k) for k in rk]
                rows = [[str(row.get(k, "")) for k in rk] for row in zt]
            else:
                headers = [f"列{i+1}" for i in range(len(zt[0]))] if zt else []
                rows = [[str(c) for c in row] for row in zt]
            table_html = '<h3 class="h3">分区统计</h3>' + self._table(headers, rows)
        return self._section_wrap("zones", num, "参数分区", "基于地形/汇合点的水文参数空间分区", info_html + img_html + table_html)

    def _section_rainfall(self, data: WatershedReportData, num: int) -> str:
        figs = data.figures
        fig_src = figs.get("rainfall") or figs.get("rainfall_distribution", "")
        info_lines = [f"<strong>{k}：</strong>{v:.4g}" if isinstance(v, float) else f"<strong>{k}：</strong>{v}" for k, v in data.rainfall_stats.items()]
        info_html = self._info_box("<br>".join(info_lines)) if info_lines else ""
        img_html = self._img(fig_src, "图 — 面雨量过程") if fig_src else ""
        return self._section_wrap("rainfall", num, "面雨量计算", "IDW 反距离加权插値", info_html + img_html)

    def _section_simulation(self, data: WatershedReportData, num: int) -> str:
        figs = data.figures
        imgs = []
        if figs.get("comparison_plot"): imgs.append(self._img(figs["comparison_plot"], "图 — 降雨-径流过程"))
        if figs.get("flow_comparison"): imgs.append(self._img(figs["flow_comparison"], "图 — 流量对比"))
        grid = []
        for key, cap in [("muskingum_example_plot", "Muskingum 法"), ("muskingum_cunge_example_plot", "Muskingum-Cunge 法"), ("uh_example_plot", "单位线法 UH")]:
            if figs.get(key): grid.append(self._img(figs[key], cap))
        if grid:
            imgs.append('<h3 class="h3">汇流方法对比</h3><div class="img-grid">' + "".join(grid) + "</div>")
        table_html = ""
        if data.simulation_metrics:
            mdesc = {"NSE": "纳什效率系数（≥0.5 为合格）", "RMSE": "均方根误差", "R2": "决定系数", "Bias": "偏差率"}
            rows = [[str(k), f"{v:.4g}" if isinstance(v, float) else str(v), mdesc.get(str(k), "")] for k, v in data.simulation_metrics.items()]
            table_html = '<h3 class="h3">模拟性能指标</h3>' + self._table(["指标", "値", "说明"], rows)
        return self._section_wrap("simulation", num, "水文模拟结果", "降雨-径流 + 汇流演算", "".join(imgs) + table_html)

    def _section_enkf(self, data: WatershedReportData, num: int) -> str:
        figs = data.figures
        grid = []
        if figs.get("enkf_parameter_convergence"): grid.append(self._img(figs["enkf_parameter_convergence"], "图 — EnKF 参数收敛过程"))
        if figs.get("enkf_flow_comparison"): grid.append(self._img(figs["enkf_flow_comparison"], "图 — EnKF 率定效果"))
        imgs_html = '<div class="img-grid">' + "".join(grid) + "</div>" if grid else ""
        table_html = ""
        em = data.enkf_metrics or {}
        if isinstance(em, dict) and em:
            if any(isinstance(v, dict) for v in em.values()):
                before, after = em.get("before", {}), em.get("after", {})
                all_keys = list(before.keys()) + [k for k in after.keys() if k not in before]
                headers = ["指标", "开环（未率定）", "EnKF 同化后", "改善幅度"]
                rows = []
                for k in all_keys:
                    b, aa = before.get(k, "—"), after.get(k, "—")
                    if isinstance(b, float) and isinstance(aa, float): rows.append([str(k), f"{b:.4g}", f"{aa:.4g}", f"{aa-b:+.4g}"])
                    else: rows.append([str(k), str(b), str(aa), "—"])
            else:
                headers = ["指标", "値"]
                rows = [[str(k), f"{v:.4g}" if isinstance(v, float) else str(v)] for k, v in em.items()]
            table_html = '<h3 class="h3">率定效果对比</h3>' + self._table(headers, rows)
        return self._section_wrap("enkf", num, "EnKF 参数率定", "集合卡尔曼滤波同化", imgs_html + table_html)

    def _section_extra(self, extra: dict, anchor: str, num: int) -> str:
        return self._section_wrap(anchor, num, extra.get("title", "自定义章节"), extra.get("subtitle", ""), extra.get("content_html", ""))
    def _section_conclusion(self, data: WatershedReportData, num: int) -> str:
        items = []
        idx = 1
        if data.area_km2:
            items.append(f'<li><span class="cn">{idx}</span>流域总面积为 <strong>{data.area_km2:.2f} km²</strong>，具备水文建模基础条件。</li>')
            idx += 1
        if data.n_subbasins:
            items.append(f'<li><span class="cn">{idx}</span>基于 DEM 共划分 <strong>{data.n_subbasins} 个子流域</strong>，空间离散化合理。</li>')
            idx += 1
        if data.elevation_range and (data.elevation_range[0] or data.elevation_range[1]):
            items.append(f'<li><span class="cn">{idx}</span>流域高程范围 <strong>{data.elevation_range[0]:.1f} ~ {data.elevation_range[1]:.1f} m</strong>，高差 {data.elevation_range[1] - data.elevation_range[0]:.1f} m。</li>')
            idx += 1
        if data.rainfall_stats:
            for k, v in data.rainfall_stats.items():
                val_str = f"{v:.4g}" if isinstance(v, float) else str(v)
                items.append(f'<li><span class="cn">{idx}</span>面雨量关键指标 <strong>{k}</strong> 为 <strong>{val_str}</strong>，IDW 插值计算结果可靠。</li>')
                idx += 1
                break
        if data.simulation_metrics:
            nse = data.simulation_metrics.get("NSE")
            if nse is not None:
                quality = "优秀" if nse >= 0.75 else ("合格" if nse >= 0.5 else "待改善")
                items.append(f'<li><span class="cn">{idx}</span>水文模拟 NSE 为 <strong>{nse:.4g}</strong>，模拟效果<strong>{quality}</strong>。</li>')
                idx += 1
        if data.n_zones:
            items.append(f'<li><span class="cn">{idx}</span>参数空间分区共 <strong>{data.n_zones} 个</strong>，有效反映水文响应空间异质性。</li>')
            idx += 1
        if not items:
            items.append('<li><span class="cn">1</span>流域水文分析已完成，各模块运行正常。</li>')
        list_html = '<ul class="conclusion-list">' + "".join(items) + "</ul>"
        outlook = self._info_box(
            "<strong>展望：</strong>后续可进一步优化模型："
            "① 引入更高分辨率 DEM 提升划分精度；"
            "② 增加雨量站密度改善插值效果；"
            "③ 采用 EnKF 集合卡尔曼滤波进行实时参数率定；"
            "④ 结合土地利用与土壤数据细化参数分区。"
        )
        return self._section_wrap("conclusion", num, "结论与展望", "主要成果总结", list_html + outlook)

    def _section_wrap(self, anchor: str, num: int, title: str, subtitle: str, body: str) -> str:
        subtitle_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
        return (
            f'<section id="{anchor}">'
            f'<div class="section-header">'
            f'<div class="snc">{num}</div>'
            f'<div><div class="section-title">{title}</div>{subtitle_html}</div>'
            f'</div>'
            f'{body}'
            f'</section>'
        )

    def _img(self, src: str, caption: str = "") -> str:
        if not src:
            return ""
        caption_div = f'<div class="img-caption">{caption}</div>' if caption else ""
        return (
            f'<div class="img-container">'
            f'<img src="{src}" alt="{caption}"/>'
            f'{caption_div}'
            f'</div>'
        )

    def _metric_card(self, value: str, label: str, color: str = "") -> str:
        cls = f"mc {color}".strip() if color else "mc"
        return (
            f'<div class="{cls}">'
            f'<div class="mv">{value}</div>'
            f'<div class="ml">{label}</div>'
            f'</div>'
        )

    def _table(self, headers: list, rows: list) -> str:
        th_html = "".join(f"<th>{h}</th>" for h in headers)
        tbody_rows = []
        for row in rows:
            td_html = "".join(f"<td>{cell}</td>" for cell in row)
            tbody_rows.append(f"<tr>{td_html}</tr>")
        return (
            '<div class="table-wrap">'
            "<table>"
            f"<thead><tr>{th_html}</tr></thead>"
            f"<tbody>{''.join(tbody_rows)}</tbody>"
            "</table>"
            "</div>"
        )

    def _info_box(self, html: str) -> str:
        return f'<div class="info-box">{html}</div>'




    def _wrap_html(self, data: WatershedReportData, nav_items: list, sections: list) -> str:
        nav_links = []
        for i, (aid, label) in enumerate(nav_items, 1):
            nav_links.append(f'<li><a href="#{aid}"><span class="nav-num">{i}</span>{label}</a></li>')
        nav_ul = "<ul>" + "".join(nav_links) + "</ul>"
        nav_html = (
            '<nav id="main-nav"><div class="nav-logo">'
            + data.name
            + f'<span class="logo-sub">水文分析报告 · {data.report_date}</span>'
            + "</div>" + nav_ul
            + '<div class="nav-footer">流域水文模型报告系统</div></nav>'
        )
        main_html = "<main>" + "".join(sections) + "</main>"
        footer_html = (
            "<footer>"
            + f"© {data.report_date[:4]} 流域水文模型报告系统"
            + f" · 自动生成于 {data.report_date}"
            + "</footer>"
        )
        menu_btn = (
            '<button class="menu-btn" onclick="'
            + "document.getElementById('main-nav').classList.toggle('open')"
            + '">☰</button>'
        )
        obs_js = (
            "<script>" + chr(10)
            + "(function(){" + chr(10)
            + "  var secs=document.querySelectorAll('section[id]');" + chr(10)
            + "  var links=document.querySelectorAll('nav ul li a');" + chr(10)
            + "  if(!secs.length||!links.length)return;" + chr(10)
            + "  var obs=new IntersectionObserver(function(entries){" + chr(10)
            + "    entries.forEach(function(e){" + chr(10)
            + "      if(e.isIntersecting){" + chr(10)
            + "        var id=e.target.getAttribute('id');" + chr(10)
            + "        links.forEach(function(a){a.classList.toggle('active',a.getAttribute('href')==='#'+id);});" + chr(10)
            + "      }" + chr(10)
            + "    });" + chr(10)
            + "  },{rootMargin:'-20% 0px -70% 0px'});" + chr(10)
            + "  secs.forEach(function(s){obs.observe(s);});" + chr(10)
            + "})();" + chr(10)
            + "</script>"
        )
        parts = [
            "<!DOCTYPE html>",
            '<html lang="zh-CN">',
            "<head>",
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            f"<title>{data.name} — 流域水文分析报告</title>",
            '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>',
            '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>',
            "<style>",
            _CSS,
            "</style>",
            "</head>",
            "<body>",
            menu_btn,
            nav_html,
            main_html,
            footer_html,
            "<script>",
            self._build_js(data),
            "</script>",
            obs_js,
            "</body>",
            "</html>",
        ]
        return chr(10).join(parts)
    def _build_js(self, data: WatershedReportData) -> str:
        sbj = json.dumps(data.subbasins_geojson or "")
        rvj = json.dumps(data.rivers_geojson or "")
        luj = json.dumps(data.landuse_geojson or "")
        soj = json.dumps(data.soil_geojson or "")
        zcj = json.dumps(data.zone_colors)
        gsj = json.dumps(data.gauging_stations)
        rgj = json.dumps(data.rain_gauges)
        mcj = json.dumps(list(data.map_center))
        mzj = json.dumps(data.map_zoom)
        js = []
        js.append("(function(){")
        js.append("function sfc(s){if(!s)return {type:\"FeatureCollection\",features:[]};try{var o=JSON.parse(s);if(o&&o.type)return o;return {type:\"FeatureCollection\",features:[]};}catch(e){return {type:\"FeatureCollection\",features:[]};} }")
        js.append("var sbFC=sfc(" + sbj + ");var rvFC=sfc(" + rvj + ");var luFC=sfc(" + luj + ");var soFC=sfc(" + soj + ");")
        js.append("var zoneColors=" + zcj + ";var gS=" + gsj + ";var rG=" + rgj + ";var mc=" + mcj + ";var mz=" + mzj + ";")
        js.append("function cCtr(fc){var lts=[],lgs=[];(fc.features||[]).forEach(function(f){function col(c){if(typeof c[0]===\"number\"){lgs.push(c[0]);lts.push(c[1]);}else c.forEach(col);}if(f.geometry&&f.geometry.coordinates)col(f.geometry.coordinates);});if(!lts.length)return [0,0];return [lts.reduce(function(a,b){return a+b;},0)/lts.length,lgs.reduce(function(a,b){return a+b;},0)/lgs.length];}")
        js.append("var center=(mc[0]===0&&mc[1]===0)?cCtr(sbFC):mc;if(center[0]===0&&center[1]===0)center=[30,110];")
        js.append("var el=document.getElementById(\"gis-map\");if(!el)return;var map=L.map(\"gis-map\").setView(center,mz);")
        js.append("var osm=L.tileLayer(\"https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png\",{attribution:\"© OSM\",maxZoom:19});")
        js.append("var sat=L.tileLayer(\"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}\",{attribution:\"© Esri\",maxZoom:19});")
        js.append("osm.addTo(map);var bM={\"OpenStreetMap\":osm,\"卫星影像\":sat};var ovl={};")
        js.append("if(sbFC.features&&sbFC.features.length>0){var sL=L.geoJSON(sbFC,{style:function(f){var z=(f.properties&&(f.properties.zone||f.properties.zone_id))||\"\";" +
                  "return {color:\"#1565C0\",weight:1.5,fillColor:zoneColors[z]||\"#90CAF9\",fillOpacity:0.45};},onEachFeature:function(f,l){var p=f.properties||{};" +
                  "var t=Object.keys(p).map(function(k){return \"<b>\"+k+\"</b>: \"+p[k];}).join(\"<br>\");if(t)l.bindPopup(t);}}).addTo(map);ovl[\"子流域分区\"]=sL;}")
        js.append("if(rvFC.features&&rvFC.features.length>0){var rL=L.geoJSON(rvFC,{style:function(){return {color:\"#1565C0\",weight:2,opacity:.85};}}).addTo(map);ovl[\"河流\"]=rL;}")
        js.append("var luC=[\"#A5D6A7\",\"#FFCC80\",\"#EF9A9A\",\"#CE93D8\",\"#80DEEA\"];var li=0;var lm={};")
        js.append("if(luFC.features&&luFC.features.length>0){var lL=L.geoJSON(luFC,{style:function(f){var k=(f.properties&&(f.properties.landuse||f.properties.type))||\"x\";if(lm[k]===undefined){lm[k]=luC[li%luC.length];li++;}return {fillColor:lm[k],weight:1,color:\"#555\",fillOpacity:0.6};}});ovl[\"土地利用\"]=lL;}")
        js.append("var soC=[\"#D7CCC8\",\"#FFAB91\",\"#B0BEC5\",\"#A5D6A7\",\"#FFF176\"];var si=0;var sm={};")
        js.append("if(soFC.features&&soFC.features.length>0){var soL=L.geoJSON(soFC,{style:function(f){var k=(f.properties&&(f.properties.soil||f.properties.type))||\"x\";if(sm[k]===undefined){sm[k]=soC[si%soC.length];si++;}return {fillColor:sm[k],weight:1,color:\"#888\",fillOpacity:0.6};}});ovl[\"土壤类型\"]=soL;}")
        js.append("if(gS&&gS.length>0){var gMs=[];gS.forEach(function(st){if(st.y==null||st.x==null)return;" +
                  "var ic=L.divIcon({className:\"\",html:\"<svg width=\\\"20\\\" height=\\\"20\\\" viewBox=\\\"0 0 20 20\\\"><polygon points=\\\"10,2 18,18 2,18\\\" fill=\\\"#e53935\\\"/></svg>\",iconSize:[20,20],iconAnchor:[10,18]});" +
                  "var m=L.marker([st.y,st.x],{icon:ic});m.bindPopup(\"<b>水文站</b><br>ID:\"+(st.id||\"\")+\"<br>类型:\"+(st.type||\"\"));gMs.push(m);});" +
                  "if(gMs.length>0){var gL=L.layerGroup(gMs);ovl[\"水文站\"]=gL;gL.addTo(map);}}")
        js.append("if(rG&&rG.length>0){var rMs=[];rG.forEach(function(rg){if(rg.y==null||rg.x==null)return;" +
                  "var ic=L.divIcon({className:\"\",html:\"<svg width=\\\"18\\\" height=\\\"18\\\" viewBox=\\\"0 0 18 18\\\"><circle cx=\\\"9\\\" cy=\\\"9\\\" r=\\\"7\\\" fill=\\\"#1565C0\\\"/></svg>\",iconSize:[18,18],iconAnchor:[9,9]});" +
                  "var m=L.marker([rg.y,rg.x],{icon:ic});m.bindPopup(\"<b>雨量站</b><br>ID:\"+(rg.id||\"\")+\"<br>类型:\"+(rg.type||\"\"));rMs.push(m);});" +
                  "if(rMs.length>0){var rL=L.layerGroup(rMs);ovl[\"雨量站\"]=rL;rL.addTo(map);}}")
        js.append("L.control.layers(bM,ovl,{collapsed:false,position:\"topright\"}).addTo(map);")
        js.append("var leg=L.control({position:\"bottomright\"});leg.onAdd=function(){var d=L.DomUtil.create(\"div\",\"\");" +
                  "d.style.cssText=\"background:rgba(255,255,255,.92);padding:10px 14px;border-radius:6px;box-shadow:0 1px 5px rgba(0,0,0,.3);font-size:12px;line-height:1.9;\";" +
                  "var h=\"<b>分区图例</b><br>\";Object.keys(zoneColors).forEach(function(z){h+=\"<span style=\\\"background:\" + zoneColors[z] + \";display:inline-block;width:12px;height:12px;border:1px solid #999;margin-right:5px;\\\"></span>\"+z+\"<br>\";});" +
                  "h+=\"<svg width=\\\"12\\\" height=\\\"12\\\" viewBox=\\\"0 0 20 20\\\"><polygon points=\\\"10,2 18,18 2,18\\\" fill=\\\"#e53935\\\"/></svg>水文站<br>\";h+=\"<svg width=\\\"12\\\" height=\\\"12\\\" viewBox=\\\"0 0 18 18\\\"><circle cx=\\\"9\\\" cy=\\\"9\\\" r=\\\"7\\\" fill=\\\"#1565C0\\\"/></svg>雨量站<br>\";d.innerHTML=h;return d;};leg.addTo(map);")
        js.append("})()")
        return chr(10).join(js)
