# coding: utf-8
from __future__ import annotations
import sys
import argparse
from pathlib import Path
import numpy as np
import plotly.graph_objects as go
import yaml
import json
import re

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "pipedream-hydrology-integration-lab"))

# Load infrastructure.py directly — package __init__ pulls optional modules (data_models) that may be absent.
import importlib.util

_infra_path = (
    PROJECT_ROOT
    / "pipedream-hydrology-integration-lab"
    / "hydromind_control_server"
    / "src"
    / "report_system"
    / "infrastructure.py"
)
_spec = importlib.util.spec_from_file_location("hm_report_infrastructure", _infra_path)
if _spec is None or _spec.loader is None or not _infra_path.is_file():
    raise ImportError(f"report infrastructure not found: {_infra_path}")
_infra_mod = importlib.util.module_from_spec(_spec)
sys.modules[str(_spec.name)] = _infra_mod
_infra_mod.__name__ = str(_spec.name)
_spec.loader.exec_module(_infra_mod)
InfrastructureRegistry = _infra_mod.InfrastructureRegistry
InfrastructureItem = _infra_mod.InfrastructureItem

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.27.0.min.js"
DARK_BG = "#0d1117"
DARK_PAPER = "#161b22"
DARK_GRID = "#30363d"
DARK_TEXT = "#c9d1d9"
ACCENT_GREEN_THEME = "#4CAF50"

def _dl(**extra) -> dict:
    d = dict(paper_bgcolor=DARK_PAPER, plot_bgcolor=DARK_BG,
             font=dict(family="Microsoft YaHei, PingFang SC, sans-serif", color=DARK_TEXT, size=12),
             margin=dict(l=60, r=40, t=60, b=60),
             xaxis=dict(gridcolor=DARK_GRID, zerolinecolor=DARK_GRID),
             yaxis=dict(gridcolor=DARK_GRID, zerolinecolor=DARK_GRID))
    d.update(extra)
    return d

def load_data(npz_path: Path) -> dict:
    data = np.load(npz_path, allow_pickle=True)
    times = data["times"]
    H_j_series = data["H_j_series"]
    z_inv = data["z_inv"]
    final_wl = data["final_wl"]
    
    order = np.argsort(-final_wl)
    z_inv_sorted = z_inv[order]
    final_wl_sorted = final_wl[order]
    H_j_series_sorted = H_j_series[:, order]
    
    total_km = float(np.max(data.get("chainages", [0]))) if "chainages" in data else 0.0
    if total_km == 0.0:
        total_km = 100.0
        
    n_nodes = len(z_inv)
    chainages = data.get("chainages", np.linspace(0.0, total_km, n_nodes))
    chainages = np.sort(chainages)
    
    depth_series = np.maximum(H_j_series_sorted - z_inv_sorted[np.newaxis, :], 0.0)
    
    return dict(times=times, H_j_series=H_j_series_sorted, z_inv=z_inv_sorted,
                final_wl=final_wl_sorted, chainages=chainages,
                depth_series=depth_series, order=order,
                total_km=total_km, n_nodes=n_nodes)

def build_registry_from_topology(case_id: str, topo_path: Path, chainages: np.ndarray) -> InfrastructureRegistry:
    items = []
    if topo_path.exists():
        with open(topo_path, "r", encoding="utf-8") as f:
            topo = yaml.safe_load(f) or {}
            
        nodes = topo.get("nodes", {})
        channels = topo.get("channels", [])
        
        for i, (name, props) in enumerate(nodes.items()):
            # infer category
            cat = "pool"
            color = "#2196F3"
            sub_type = ""
            
            if "泵" in name or "站" in name:
                cat = "pump"
                color = "#4CAF50"
            elif "闸" in name:
                cat = "gate"
                color = "#F44336"
            elif "阀" in name:
                cat = "valve"
                color = "#FF9800"
            elif "分水" in name or "退水" in name:
                cat = "diversion"
                color = "#FF5722"
            elif "水库" in name or "湖" in name or "池" in name:
                cat = "pool"
                color = "#1565C0"
                
            c_km = chainages[i] if i < len(chainages) else chainages[-1]
            
            items.append(InfrastructureItem(
                chainage_km=c_km,
                name=name,
                category=cat,
                sub_type=sub_type,
                color=color,
            ))
            
        # Add channels
        for i, ch in enumerate(channels):
            if not isinstance(ch, dict): continue
            name = ch.get("name", f"Channel {i}")
            cat = "pipe"
            color = "#00ACC1"
            if "隧洞" in name or "暗涵" in name:
                cat = "tunnel"
                color = "#6D4C41"
            elif "倒虹吸" in name or "顶管" in name:
                cat = "siphon"
                color = "#00BCD4"
                
            c_km = chainages[min(i, len(chainages)-1)]
            c_end_km = chainages[min(i+1, len(chainages)-1)] if i+1 < len(chainages) else c_km + 5.0
            
            items.append(InfrastructureItem(
                chainage_km=c_km,
                chainage_end_km=c_end_km,
                name=name,
                category=cat,
                color=color
            ))

    return InfrastructureRegistry(project_name=case_id, items=items)


def chapter0_overview(reg: InfrastructureRegistry, data_dict: dict) -> str:
    n_t = len(reg.get_by_category("tunnel"))
    n_s = len(reg.get_by_category("siphon"))
    n_g = len(reg.get_by_category("gate"))
    n_d = len(reg.get_by_category("diversion"))
    n_v = len(reg.get_by_category("valve"))
    
    total_km = data_dict["total_km"]
    n_nodes = data_dict["n_nodes"]
    sim_hours = data_dict["times"][-1] if len(data_dict["times"]) > 0 else 0
    n_frames = len(data_dict["times"])
    
    kpis = [
        ("总输水长度", f"{total_km:.0f} km"),
        ("模型节点数", f"{n_nodes} 个"),
        ("仿真时长", f"{sim_hours:.1f} h"),
        ("时间步数", f"{n_frames} 帧"),
        ("控制设施", f"{len(reg.items)} 项"),
    ]
    kpi_html = "".join(
        f"<div class=kpi-card><div class=kpi-value>{v}</div><div class=kpi-label>{k}</div></div>"
        for k, v in kpis
    )
    
    def _end_str(it) -> str:
        if it.chainage_end_km is not None:
            return f"{it.chainage_km:.1f}~{it.chainage_end_km:.1f} km"
        return "-"
        
    infra_rows = "".join(
        f"<tr><td>{it.chainage_km:.1f}</td><td><span style=color:{it.color}>{it.name}</span></td>"
        f"<td>{it.category}</td><td>{it.sub_type or chr(45)}</td><td>{_end_str(it)}</td></tr>"
        for it in reg.items
    )
    n = len(reg.items)
    return (
        "<section id=ch0 class=chapter>"
        "<h2 class=chapter-title>第0章 工程概览</h2>"
        f"<div class=kpi-grid>{kpi_html}</div>"
        f"<h3>基础设施清单 ({n} 项)</h3>"
        "<table class=data-table><thead><tr>"
        "<th>里程 (km)</th><th>名称</th><th>类型</th><th>细分</th><th>范围</th>"
        f"</tr></thead><tbody>{infra_rows}</tbody></table>"
        "</section>"
    )

def chapter1_hgl(d: dict, reg: InfrastructureRegistry) -> str:
    chainages = d["chainages"]
    z_inv = d["z_inv"]
    final_wl = d["final_wl"]
    total_km = d["total_km"]

    fig = go.Figure()
    reg.add_plotly_background_bands(fig)
    fig.add_trace(go.Scatter(
        x=chainages.tolist(), y=z_inv.tolist(),
        name="底高程", fill="tozeroy",
        fillcolor="rgba(100,80,60,0.4)",
        line=dict(color="rgba(120,90,60,0.8)", width=1),
    ))
    fig.add_trace(go.Scatter(
        x=chainages.tolist(), y=final_wl.tolist(),
        name=f"水面线",
        line=dict(color=ACCENT_GREEN_THEME, width=2.5),
    ))
    
    reg.add_plotly_annotations(fig)
    fig.update_layout(**_dl(
        title=dict(text="稳态水面线", font=dict(size=16, color=DARK_TEXT)),
        xaxis=dict(title="里程 (km)", range=[0, total_km], gridcolor=DARK_GRID),
        yaxis=dict(title="高程 (m)", gridcolor=DARK_GRID),
        height=750, autosize=True,
    ))
    inner = fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
    return "<section id=ch1 class=chapter><h2 class=chapter-title>第1章 稳态水面线</h2>" + inner + "</section>"

def chapter2_animation(d: dict, reg: InfrastructureRegistry) -> str:
    chainages = d["chainages"]
    z_inv = d["z_inv"]
    H_j_series = d["H_j_series"]
    times = d["times"]
    total_km = d["total_km"]
    n_frames = len(times)
    wl0 = H_j_series[0] if n_frames > 0 else np.zeros_like(z_inv)

    fig = go.Figure()
    reg.add_plotly_background_bands(fig)
    fig.add_trace(go.Scatter(
        x=chainages.tolist(), y=z_inv.tolist(), name="底高程",
        fill="tozeroy", fillcolor="rgba(100,80,60,0.4)",
        line=dict(color="rgba(120,90,60,0.8)", width=1),
    ))
    fig.add_trace(go.Scatter(
        x=chainages.tolist(),
        y=wl0.tolist(),
        name="水面线", line=dict(color=ACCENT_GREEN_THEME, width=2.5),
    ))
    
    if n_frames > 0:
        fig.frames = [
            go.Frame(
                data=[
                    go.Scatter(y=H_j_series[i].tolist()),
                ],
                traces=[1],
                name=f"t={times[i]:.1f}h",
                layout=go.Layout(title_text=f"非恒定流水面线  t = {times[i]:.1f} h"),
            )
            for i in range(n_frames)
        ]
        sliders = [{
            "steps": [{
                "args": [[f"t={times[i]:.1f}h"],
                          {"frame": {"duration": 200, "redraw": True},
                           "mode": "immediate", "transition": {"duration": 100}}],
                "label": f"t={times[i]:.1f}h", "method": "animate",
            } for i in range(n_frames)],
            "active": 0, "x": 0.05, "y": 0, "len": 0.9,
            "bgcolor": DARK_PAPER, "font": {"color": DARK_TEXT, "size": 9},
            "currentvalue": {"prefix": "时刻: ", "font": {"color": ACCENT_GREEN_THEME}},
        }]
        buttons = [{
            "type": "buttons",
            "buttons": [
                {"label": "Play", "method": "animate",
                 "args": [None, {"frame": {"duration": 300, "redraw": True},
                                  "fromcurrent": True, "transition": {"duration": 150}}]},
                {"label": "Pause", "method": "animate",
                 "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}]},
            ],
            "x": 0.0, "y": -0.12, "bgcolor": DARK_PAPER, "font": {"color": DARK_TEXT},
        }]
        fig.update_layout(sliders=sliders, updatemenus=buttons)

    reg.add_plotly_annotations(fig)
    fig.update_layout(**_dl(
        title=dict(text=f"非恒定流水面线  t = {times[0]:.1f} h" if n_frames > 0 else "非恒定流水面线",
                   font=dict(size=16, color=DARK_TEXT)),
        xaxis=dict(title="里程 (km)", range=[0, total_km], gridcolor=DARK_GRID),
        yaxis=dict(title="高程 (m)", gridcolor=DARK_GRID),
        height=750, autosize=True,
        legend=dict(bgcolor="rgba(22,27,34,0.8)", bordercolor=DARK_GRID),
    ))
    import json, re as _re
    inner = fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
    div_id_m = _re.search(r'id="([a-f0-9-]+)"', inner)
    div_id = div_id_m.group(1) if div_id_m else "ch2plot"
    fig_json = json.loads(fig.to_json())
    frames_js = json.dumps(fig_json.get("frames", []))
    inject = (
        f"<script>Plotly.addFrames('{div_id}', {frames_js});</script>"
    )
    return (
        "<section id=ch2 class=chapter>"
        f"<h2 class=chapter-title>第2章 非恒定流动画</h2>"
        + inner + inject + "</section>"
    )

def chapter3_timeseries(d: dict, reg: InfrastructureRegistry) -> str:
    chainages = d["chainages"]
    H_j_series = d["H_j_series"]
    times = d["times"]
    
    key_items = [item for item in reg.items if item.category in ("gate", "pump", "pool", "valve")]
    if len(key_items) > 10:
        indices = np.linspace(0, len(key_items)-1, 10).astype(int)
        key_items = [key_items[i] for i in indices]
        
    fig = go.Figure()
    for item in key_items:
        km = item.chainage_km
        label = item.name
        color = item.color
        idx = int(np.argmin(np.abs(chainages - km)))
        if idx < H_j_series.shape[1]:
            wl_ts = H_j_series[:, idx]
            fig.add_trace(go.Scatter(
                x=times.tolist(), y=wl_ts.tolist(),
                name=f"{label} ({km:.1f}km)",
                line=dict(color=color, width=2),
                hovertemplate=f"{label}<br>t: %{{x:.1f}} h<br>水位: %{{y:.2f}} m<extra></extra>",
            ))
            
    fig.update_layout(**_dl(
        title=dict(text="关键节点水位过程线",
                   font=dict(size=16, color=DARK_TEXT)),
        xaxis=dict(title="时间 (h)", gridcolor=DARK_GRID),
        yaxis=dict(title="水位 (m)", gridcolor=DARK_GRID),
        height=650, autosize=True, hovermode="x unified",
        legend=dict(bgcolor="rgba(22,27,34,0.8)", bordercolor=DARK_GRID,
                    orientation="v", x=1.01, y=1),
    ))
    inner = fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
    return (
        "<section id=ch3 class=chapter>"
        "<h2 class=chapter-title>第3章 关键节点水位过程线</h2>"
        + inner + "</section>"
    )

def chapter4_heatmap(d: dict, reg: InfrastructureRegistry) -> str:
    chainages = d["chainages"]
    depth_series = d["depth_series"]
    times = d["times"]
    total_km = d["total_km"]
    
    fig = go.Figure(data=go.Heatmap(
        x=chainages.tolist(), y=times.tolist(), z=depth_series.tolist(),
        colorscale="Blues",
        colorbar=dict(
            title=dict(text="水深 (m)", font=dict(color=DARK_TEXT)),
            tickfont=dict(color=DARK_TEXT),
        ),
        hovertemplate="里程: %{x:.1f} km<br>时间: %{y:.1f} h<br>水深: %{z:.2f} m<extra></extra>",
        zmin=0,
    ))
    
    for item in reg.items:
        if item.category in ("pump", "pool", "valve"):
            fig.add_vline(x=item.chainage_km, line_dash="dash", line_color=item.color, line_width=1.5,
                          annotation_text=item.name,
                          annotation_font_color=item.color, annotation_font_size=10)
                          
    fig.update_layout(**_dl(
        title=dict(text="水深时空分布热图",
                   font=dict(size=16, color=DARK_TEXT)),
        xaxis=dict(title="里程 (km)", range=[0, total_km], gridcolor=DARK_GRID),
        yaxis=dict(title="时间 (h)", gridcolor=DARK_GRID),
        height=650, autosize=True,
    ))
    inner = fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
    return (
        "<section id=ch4 class=chapter>"
        "<h2 class=chapter-title>第4章 水深时空热图</h2>"
        + inner + "</section>"
    )

def chapter5_odd(odd_data: dict) -> str:
    if not odd_data:
        return ""
        
    metrics = odd_data.get("coverage_metrics", {})
    total = metrics.get("total_scenarios_tested", 0)
    oob = metrics.get("out_of_bounds_triggered", 0)
    rec_rate = metrics.get("recovery_success_rate", 0.0)
    
    kpis = [
        ("测试场景总数", f"{total}"),
        ("越限触发次数", f"{oob}"),
        ("安全恢复率", f"{rec_rate*100:.1f}%"),
    ]
    kpi_html = "".join(
        f"<div class=kpi-card><div class=kpi-value>{v}</div><div class=kpi-label>{k}</div></div>"
        for k, v in kpis
    )
    
    scenarios = odd_data.get("scenarios", [])
    rows = ""
    for sc in scenarios:
        sid = sc.get("scenario_id", "-")
        desc = sc.get("description", "-")
        state = sc.get("state", "-")
        in_bounds = "是" if sc.get("in_bounds") else "否"
        rec = sc.get("recovery_action", "-")
        rows += f"<tr><td>{sid}</td><td>{desc}</td><td>{state}</td><td>{in_bounds}</td><td>{rec}</td></tr>"
        
    table_html = (
        "<h3>ODD 场景生成策略与边界验证</h3>"
        "<table class=data-table><thead><tr>"
        "<th>场景ID</th><th>描述</th><th>状态</th><th>是否在界内</th><th>恢复策略</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    
    return (
        "<section id=ch5 class=chapter>"
        "<h2 class=chapter-title>第5章 ODD 运行设计域评估</h2>"
        f"<div class=kpi-grid>{kpi_html}</div>"
        + table_html + "</section>"
    )

def chapter6_sil(sil_data: dict) -> str:
    if not sil_data:
        return ""
        
    count = sil_data.get("scenario_count", 0)
    overall_pass = sil_data.get("overall_pass_rate", 0.0)
    qg = "通过" if sil_data.get("quality_gate_passed") else "未通过"
    
    kpis = [
        ("SIL 验证场景数", f"{count}"),
        ("综合通过率", f"{overall_pass*100:.1f}%"),
        ("质量门禁状态", f"{qg}"),
    ]
    kpi_html = "".join(
        f"<div class=kpi-card><div class=kpi-value>{v}</div><div class=kpi-label>{k}</div></div>"
        for k, v in kpis
    )
    
    modules = sil_data.get("modules", {})
    rows = ""
    for m, m_data in modules.items():
        pass_rate = m_data.get("pass_rate", 0.0)
        note = m_data.get("note", "-")
        rows += f"<tr><td>{m}</td><td>{pass_rate*100:.1f}%</td><td>{note}</td></tr>"
        
    table_html = (
        "<h3>多场景 SIL 验证指标</h3>"
        "<table class=data-table><thead><tr>"
        "<th>模块</th><th>通过率</th><th>说明</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    
    return (
        "<section id=ch6 class=chapter>"
        "<h2 class=chapter-title>第6章 软件在环 (SIL) 验证</h2>"
        f"<div class=kpi-grid>{kpi_html}</div>"
        + table_html + "</section>"
    )

def chapter7_wnal(d: dict) -> str:
    if not d: return ""
    
    main_dims = d.get("main_dimensions", {})
    if not main_dims: return ""
    
    categories = []
    scores = []
    levels = []
    
    sub_scores = []
    for m in ["capability", "safety", "governance"]:
        sub_scores.extend(main_dims.get(m, {}).get("sub_scores", []))
        
    if not sub_scores: return ""
    
    for sub in sub_scores:
        categories.append(f"{sub['code']} {sub['name']}")
        scores.append(sub['score'])
        levels.append(sub['level'])
        
    # Close the loop
    categories.append(categories[0])
    scores.append(scores[0])
    levels.append(levels[0])
    
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=scores,
        theta=categories,
        fill='toself',
        name='得分',
        line=dict(color=ACCENT_GREEN_THEME),
        fillcolor="rgba(76, 175, 80, 0.3)"
    ))
    fig.update_layout(**_dl(
        title=dict(text="WNAL 12维评价雷达图", font=dict(size=16, color=DARK_TEXT)),
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 5], gridcolor=DARK_GRID),
            angularaxis=dict(gridcolor=DARK_GRID),
            bgcolor=DARK_PAPER
        ),
        showlegend=False,
        height=600, autosize=True,
        paper_bgcolor=DARK_PAPER,
        plot_bgcolor=DARK_BG
    ))
    
    inner = fig.to_html(full_html=False, include_plotlyjs=False, config={"responsive": True})
    
    rows = ""
    for sub in sub_scores:
        gaps = "<br>".join(sub.get("gaps", [])) or "-"
        recs = "<br>".join(sub.get("recommendations", [])) or "-"
        rows += f"<tr><td>{sub['code']}</td><td>{sub['name']}</td><td>{sub['score']:.2f}</td><td>L{sub['level']}</td><td>{gaps}</td><td>{recs}</td></tr>"
        
    table_html = (
        "<h3>维度明细</h3>"
        "<table class=data-table><thead><tr>"
        "<th>编号</th><th>维度</th><th>得分</th><th>等级</th><th>短板</th><th>建议</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    
    summary = d.get("summary", "")
    summary_html = f"<div style='margin-bottom: 20px; padding: 15px; background: {DARK_PAPER}; border-left: 4px solid {ACCENT_GREEN_THEME};'>{summary}</div>"
    
    return (
        "<section id=ch7 class=chapter>"
        "<h2 class=chapter-title>第7章 WNAL 智能化等级评价</h2>"
        + summary_html + inner + table_html + "</section>"
    )

_CSS = (
    "* { box-sizing: border-box; margin: 0; padding: 0; }"
    + "body { font-family: Microsoft YaHei, PingFang SC, sans-serif; background: " + DARK_BG + "; color: " + DARK_TEXT + "; display: flex; }"
    + ".side-nav { position: fixed; top: 0; right: 0; width: 200px; height: 100vh; background: " + DARK_PAPER + "; border-left: 1px solid " + DARK_GRID + "; padding: 20px 12px; overflow-y: auto; z-index: 1000; }"
    + ".side-nav ul { list-style: none; } .side-nav li { margin: 8px 0; }"
    + ".side-nav .nav-link { color: " + DARK_TEXT + "; text-decoration: none; font-size: 12px; display: block; padding: 4px 8px; border-radius: 4px; }"
    + ".side-nav .nav-link:hover { background: " + DARK_GRID + "; color: " + ACCENT_GREEN_THEME + "; }"
    + ".main-content { margin-right: 210px; padding: 30px 40px; max-width: 1200px; flex: 1; }"
    + ".report-header { border-bottom: 2px solid " + ACCENT_GREEN_THEME + "; padding-bottom: 20px; margin-bottom: 30px; }"
    + ".report-header h1 { font-size: 28px; color: " + ACCENT_GREEN_THEME + "; margin-bottom: 6px; }"
    + ".report-header .subtitle { color: #8b949e; font-size: 14px; }"
    + ".chapter { padding: 30px 0; border-bottom: 1px solid " + DARK_GRID + "; }"
    + ".chapter-title { font-size: 22px; color: " + ACCENT_GREEN_THEME + "; margin-bottom: 20px; padding-left: 12px; border-left: 4px solid " + ACCENT_GREEN_THEME + "; }"
    + ".plotly-graph-div { width: 100% !important; }"
    + ".chart-wrap { width: 100%; overflow: hidden; margin: 10px 0; }"
    + "h3 { font-size: 16px; color: " + DARK_TEXT + "; margin: 20px 0 10px; }"
    + ".kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }"
    + ".kpi-card { background: " + DARK_PAPER + "; border: 1px solid " + DARK_GRID + "; border-radius: 8px; padding: 16px; text-align: center; }"
    + ".kpi-value { font-size: 20px; font-weight: bold; color: " + ACCENT_GREEN_THEME + "; margin-bottom: 4px; }"
    + ".kpi-label { font-size: 12px; color: #8b949e; }"
    + ".data-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }"
    + ".data-table th { background: " + DARK_PAPER + "; border: 1px solid " + DARK_GRID + "; padding: 8px 12px; text-align: left; color: " + ACCENT_GREEN_THEME + "; }"
    + ".data-table td { border: 1px solid " + DARK_GRID + "; padding: 6px 12px; vertical-align: middle; }"
    + ".data-table tr:hover td { background: rgba(88,166,255,.05); }"
)

def _build_nav(chapters: list) -> str:
    items = "".join(
        f"<li><a href=#{cid} class=nav-link>{title}</a></li>"
        for cid, title in chapters
    )
    return f"<nav class=side-nav><ul>{items}</ul></nav>"

def _build_full_html(body: str, nav: str, project_name: str) -> str:
    return (
        "<!DOCTYPE html><html lang=zh-CN><head>"
        "<meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{project_name} 仿真报告</title>"
        f"<script src={PLOTLY_CDN}></script>"
        f"<style>{_CSS}</style>"
        "</head><body>"
        f"{nav}"
        "<div class=main-content>"
        "<div class=report-header>"
        f"<h1>{project_name} — 完整仿真报告</h1>"
        f"<div class=subtitle>通用动态生成报告 &middot; 基于基础设施注册表与拓扑</div>"
        "</div>"
        f"{body}"
        "</div></body></html>"
    )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--npz-path", required=True, type=Path)
    parser.add_argument("--output-path", required=True, type=Path)
    args = parser.parse_args()

    print(f"开始生成 {args.case_id} 通用仿真报告...")
    if not args.npz_path.exists():
        print(f"Warning: 仿真数据文件不存在: {args.npz_path}，使用模拟数据进行测试。")
        d = {"total_km": 100.0, "n_nodes": 10, "times": np.linspace(0, 72, 10), "chainages": np.linspace(0, 100, 10), "z_inv": np.zeros(10), "final_wl": np.ones(10)*10, "H_j_series": np.zeros((10, 10)), "depth_series": np.zeros((10, 10))}
    else:
        d = load_data(args.npz_path)
    
    topo_path = PROJECT_ROOT / f"Hydrology/knowledge/{args.case_id}/topology/topology.yaml"
    reg = build_registry_from_topology(args.case_id, topo_path, d["chainages"])
    
    contracts_dir = PROJECT_ROOT / "cases" / args.case_id / "contracts"
    
    # 1. ODD
    odd_file = contracts_dir / "odd_evaluation.latest.json"
    if not odd_file.exists():
        odd_file = contracts_dir / "odd_coverage_report.json"
    odd_data = {}
    if odd_file.exists():
        try:
            with open(odd_file, "r", encoding="utf-8") as f:
                odd_data = json.load(f)
        except Exception:
            pass

    # 2. SIL
    sil_file = contracts_dir / "strict_revalidation_summary.json"
    if not sil_file.exists():
        sil_file = contracts_dir / "control.latest.json"
    if not sil_file.exists():
        sil_file = PROJECT_ROOT / "reports" / "acceptance" / "strict_revalidation_summary.json"
    sil_data = {}
    if sil_file.exists():
        try:
            with open(sil_file, "r", encoding="utf-8") as f:
                sil_data = json.load(f)
        except Exception:
            pass

    # 3. WNAL
    wnal_file = contracts_dir / "wnal_evaluation.latest.json"
    wnal_data = {}
    if wnal_file.exists():
        try:
            with open(wnal_file, "r", encoding="utf-8") as f:
                wnal_data = json.load(f)
        except Exception:
            pass
    if not wnal_data:
        ext_file = contracts_dir / "outcomes" / "wnal_evaluation_ext.latest.json"
        if ext_file.exists():
            try:
                with open(ext_file, "r", encoding="utf-8") as f:
                    ext_data = json.load(f)
                    stdout = ext_data.get("dimensions", {}).get("result", [{}])[0].get("value", {}).get("stdout", "")
                    m = re.search(r"报告: (.*_wnal_evaluation\.json)", stdout)
                    if m:
                        real_wnal_file = Path(m.group(1))
                        if real_wnal_file.exists():
                            with open(real_wnal_file, "r", encoding="utf-8") as f2:
                                wnal_data = json.load(f2)
            except Exception:
                pass
    if not wnal_data:
        lab_dir = PROJECT_ROOT / "pipedream-hydrology-integration-lab" / "research" / "wnal_evaluation"
        if lab_dir.exists():
            for pf in lab_dir.rglob("*_wnal_evaluation.json"):
                if args.case_id in pf.name: # basic heuristic
                    try:
                        with open(pf, "r", encoding="utf-8") as f2:
                            wnal_data = json.load(f2)
                        break
                    except Exception:
                        pass
    
    chapters_meta = [
        ("ch0", "第0章 工程概览"),
        ("ch1", "第1章 水面线"),
        ("ch2", "第2章 非恒定流动画"),
        ("ch3", "第3章 水位过程线"),
        ("ch4", "第4章 水深热图"),
    ]
    if odd_data:
        chapters_meta.append(("ch5", "第5章 ODD 评估"))
    if sil_data:
        chapters_meta.append(("ch6", "第6章 SIL 验证"))
    if wnal_data:
        chapters_meta.append(("ch7", "第7章 WNAL 评价"))
        
    nav = _build_nav(chapters_meta)
    
    parts = [
        chapter0_overview(reg, d),
        chapter1_hgl(d, reg),
        chapter2_animation(d, reg),
        chapter3_timeseries(d, reg),
        chapter4_heatmap(d, reg),
    ]
    if odd_data:
        parts.append(chapter5_odd(odd_data))
    if sil_data:
        parts.append(chapter6_sil(sil_data))
    if wnal_data:
        parts.append(chapter7_wnal(wnal_data))
    
    html = _build_full_html("".join(parts), nav, reg.project_name)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(html, encoding="utf-8")
    print(f"[Complete] Report written: {args.output_path}")

if __name__ == "__main__":
    main()
