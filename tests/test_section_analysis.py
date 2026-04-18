# ALGORITHM_REGISTRY:
#   id: test_section_analysis
#   category: hydrology
#   protocol: HydrologyProduct
#   case_types: [cascade_hydro, water_transfer]
#   source_project: hydrology
"""Unit tests for hydro_model.section_analysis (synthetic data only, no external files)."""

from __future__ import annotations

import pytest

from hydro_model.section_analysis import (
    PARSER_REGISTRY,
    build_hydraulic_curve,
    build_reservoir_ah_curve,
    compute_area,
    compute_hydraulic_properties,
    compute_wetted_perimeter,
    compute_width,
    evaluate_sections,
    get_parser,
    run_section_pipeline,
)
from hydro_model.section_analysis.base import SectionProfile
from hydro_model.section_analysis.config import SectionAnalysisConfig
from hydro_model.section_analysis.evaluator import evaluate_section_quality, result_to_dict


# --- Synthetic cross-sections -------------------------------------------------

# Stepped channel from spec: bottom segment (10,0)-(20,0) is 10 m → A = 10×3 = 30 at wl=3.
YZ_STEPPED_CHANNEL = [[0, 5], [10, 5], [10, 0], [20, 0], [20, 5], [30, 5]]

# True rectangle: 20 m bottom width, vertical banks to z=5 → A = 20×3 = 60 at wl=3.
YZ_RECT_20M_BOTTOM = [[0, 0], [20, 0], [20, 5], [0, 5]]


class TestHydraulicsComputeArea:
    def test_stepped_channel_area_at_water_level_3(self) -> None:
        assert compute_area(YZ_STEPPED_CHANNEL, 3.0) == pytest.approx(30.0)

    def test_rectangular_twenty_meter_bottom_matches_width_times_depth(self) -> None:
        """底宽 20 m、水深 3 m → A ≈ 20×3 = 60（与教材矩形断面公式一致）。"""
        assert compute_area(YZ_RECT_20M_BOTTOM, 3.0) == pytest.approx(60.0)

    def test_water_level_below_channel_bed_returns_zero(self) -> None:
        assert compute_area(YZ_RECT_20M_BOTTOM, -1.0) == 0.0
        assert compute_area(YZ_STEPPED_CHANNEL, 0.0) == 0.0

    def test_empty_yz_returns_zero(self) -> None:
        assert compute_area([], 100.0) == 0.0
        assert compute_area([[0, 0]], 1.0) == 0.0


class TestHydraulicsComputeWettedPerimeter:
    def test_empty_or_single_point_returns_zero(self) -> None:
        assert compute_wetted_perimeter([], 3.0) == 0.0
        assert compute_wetted_perimeter([[0, 0]], 3.0) == 0.0

    def test_below_bed_returns_zero(self) -> None:
        assert compute_wetted_perimeter(YZ_RECT_20M_BOTTOM, -0.5) == 0.0

    def test_rectangle_positive_wetted_perimeter(self) -> None:
        p = compute_wetted_perimeter(YZ_RECT_20M_BOTTOM, 3.0)
        assert p > 0.0
        assert p == pytest.approx(23.0)


class TestHydraulicsComputeWidth:
    def test_empty_or_single_point_returns_zero(self) -> None:
        assert compute_width([], 3.0) == 0.0
        assert compute_width([[0, 0]], 3.0) == 0.0

    def test_stepped_channel_surface_width_at_wl_3(self) -> None:
        assert compute_width(YZ_STEPPED_CHANNEL, 3.0) == pytest.approx(10.0)

    def test_rectangle_full_bottom_width_when_wet(self) -> None:
        assert compute_width(YZ_RECT_20M_BOTTOM, 3.0) == pytest.approx(20.0)


class TestHydraulicsComputeHydraulicProperties:
    def test_matches_components(self) -> None:
        wl = 3.0
        hp = compute_hydraulic_properties(YZ_RECT_20M_BOTTOM, wl, manning_n=0.025, slope=0.001)
        assert hp.H == wl
        assert hp.A == pytest.approx(compute_area(YZ_RECT_20M_BOTTOM, wl))
        assert hp.P == pytest.approx(compute_wetted_perimeter(YZ_RECT_20M_BOTTOM, wl))
        assert hp.B == pytest.approx(compute_width(YZ_RECT_20M_BOTTOM, wl))
        assert hp.R == pytest.approx(hp.A / hp.P if hp.P > 0 else 0.0)
        assert hp.Q >= 0.0


class TestHydraulicsBuildHydraulicCurve:
    def test_respects_n_levels_and_curve_keys(self) -> None:
        curve = build_hydraulic_curve(
            YZ_RECT_20M_BOTTOM,
            z_min=1.0,
            z_max=4.0,
            n_levels=5,
            manning_n=0.025,
            slope=0.001,
            curves=["A", "P", "B", "R", "Q"],
        )
        assert len(curve) == 5
        for pt in curve:
            assert "H" in pt
            assert "A" in pt and "P" in pt and "B" in pt and "R" in pt and "Q" in pt


class TestHydraulicsBuildReservoirAhCurve:
    def test_multi_section_trapezoidal_integration_along_reach(self) -> None:
        """两断面同宽、沿程 1000 m：A(H) ≈ 平均水面宽 × 河长。"""
        yz = YZ_RECT_20M_BOTTOM
        s0 = SectionProfile(
            id="s0",
            name="s0",
            yz=[list(p) for p in yz],
            location=0.0,
            channel="main",
            station="st1",
        )
        s1 = SectionProfile(
            id="s1",
            name="s1",
            yz=[list(p) for p in yz],
            location=1000.0,
            channel="main",
            station="st1",
        )
        curve = build_reservoir_ah_curve([s1, s0], z_min=2.0, z_max=2.0, n_levels=1)
        assert len(curve) == 1
        row = curve[0]
        assert row["H"] == pytest.approx(2.0)
        # width 20 at wl=2 for this yz → integral = 20 * 1000 = 20000 m²
        assert row["A_m2"] == pytest.approx(20000.0, rel=1e-3)
        assert row["n_wet_sections"] == 2
        assert row["A_km2"] == pytest.approx(row["A_m2"] / 1e6)


class TestHydraulicsEvaluateSections:
    def test_empty_sections(self) -> None:
        out = evaluate_sections([])
        assert out["status"] == "empty"
        assert out["n_sections"] == 0

    def test_non_empty_summary_keys(self) -> None:
        s = SectionProfile(
            id="a",
            name="a",
            yz=[list(p) for p in YZ_RECT_20M_BOTTOM],
            location=0.0,
            channel="c",
            station="s",
            source_type="synthetic",
        )
        out = evaluate_sections([s])
        assert out["n_sections"] == 1
        assert "z_bed_range" in out and "width_range" in out


class TestSectionProfilePostInit:
    def test_auto_z_min_z_max_width_n_points(self) -> None:
        s = SectionProfile(
            id="p1",
            name="p1",
            yz=[[0.0, 1.0], [10.0, 0.0], [20.0, 2.0]],
        )
        assert s.z_min == pytest.approx(0.0)
        assert s.z_max == pytest.approx(2.0)
        assert s.n_points == 3
        assert s.width == pytest.approx(20.0)


class TestSectionAnalysisConfigFromCaseConfig:
    def test_builds_from_nested_dict(self) -> None:
        cfg = {
            "case_id": "demo_case",
            "section_analysis": {
                "n_levels": 15,
                "manning_n_default": 0.03,
                "output_curves": ["A", "B"],
                "sources": [{"type": "wxq_json", "path": "x.json"}],
            },
            "knowledge": {
                "topology": {
                    "channels": [{"id": "c1"}],
                },
                "reservoirs": {
                    "R1": {
                        "station_id": "sta1",
                        "normal_pool": 100.0,
                        "dead_pool": 80.0,
                    },
                },
            },
        }
        sac = SectionAnalysisConfig.from_case_config(cfg)
        assert sac.case_id == "demo_case"
        assert sac.n_levels == 15
        assert sac.manning_n_default == pytest.approx(0.03)
        assert sac.output_curves == ["A", "B"]
        assert len(sac.sources) == 1
        assert sac.channels == [{"id": "c1"}]
        assert sac.reservoir_levels["sta1"]["normal_pool"] == pytest.approx(100.0)
        assert sac.reservoir_levels["sta1"]["dead_pool"] == pytest.approx(80.0)


class TestEvaluateSectionQuality:
    def test_returns_five_dimensions(self) -> None:
        yz = [list(p) for p in YZ_RECT_20M_BOTTOM]
        sections = [
            SectionProfile(
                id="s1",
                name="s1",
                yz=yz,
                location=0.0,
                channel="ch",
                station="sta1",
                source_type="syn",
                n_points=len(yz),
            ),
            SectionProfile(
                id="s2",
                name="s2",
                yz=yz,
                location=500.0,
                channel="ch",
                station="sta1",
                source_type="syn",
                n_points=len(yz),
            ),
        ]
        case_cfg = {
            "case_id": "t",
            "section_analysis": {},
            "knowledge": {
                "topology": {"channels": []},
                "reservoirs": {
                    "R": {
                        "station_id": "sta1",
                        "normal_pool": 4.0,
                        "dead_pool": 0.5,
                    },
                },
            },
        }
        config = SectionAnalysisConfig.from_case_config(case_cfg)
        result = evaluate_section_quality(sections, config)
        assert len(result.dimensions) == 5
        names = [d.name for d in result.dimensions]
        assert names == [
            "coverage",
            "density",
            "resolution",
            "consistency",
            "hydraulic_fitness",
        ]
        assert 0.0 <= result.overall_score <= 1.0
        assert result.grade in {"A", "B", "C", "D"}


class TestResultToDict:
    def test_shape_and_dimension_entries(self) -> None:
        from hydro_model.section_analysis.evaluator import EvaluationDimension, SectionEvaluationResult

        dims = [
            EvaluationDimension("coverage", 1.0, detail="ok"),
            EvaluationDimension("density", 0.9, detail="ok"),
            EvaluationDimension("resolution", 0.8, detail="ok"),
            EvaluationDimension("consistency", 0.7, detail="ok"),
            EvaluationDimension("hydraulic_fitness", 0.6, detail="ok"),
        ]
        r = SectionEvaluationResult(
            case_id="c",
            n_sections=2,
            n_stations=1,
            n_channels=1,
            dimensions=dims,
            overall_score=0.85,
            grade="A",
            warnings=["w"],
            recommendations=["r"],
        )
        d = result_to_dict(r)
        assert d["case_id"] == "c"
        assert d["evaluation_type"] == "section_quality"
        assert d["n_sections"] == 2
        assert d["n_stations"] == 1
        assert d["n_channels"] == 1
        assert d["overall_score"] == 0.85
        assert d["grade"] == "A"
        assert d["warnings"] == ["w"]
        assert d["recommendations"] == ["r"]
        assert len(d["dimensions"]) == 5
        for i, row in enumerate(d["dimensions"]):
            assert row == {
                "name": dims[i].name,
                "score": dims[i].score,
                "max_score": dims[i].max_score,
                "detail": dims[i].detail,
            }


class TestParserRegistry:
    def test_expected_parser_keys_registered(self) -> None:
        for key in ("wxq_json", "terrain_txt", "wxq_terrain_txt", "xlsx_terrain"):
            assert key in PARSER_REGISTRY

    def test_get_parser_returns_callable_instance(self) -> None:
        p = get_parser("wxq_json")
        assert hasattr(p, "parse")


class TestRunSectionPipeline:
    def test_empty_sources_returns_structure(self) -> None:
        config = SectionAnalysisConfig(case_id="empty", sources=[])
        out = run_section_pipeline(config, workspace_root=".")
        assert out["case_id"] == "empty"
        assert out["n_sections_total"] == 0
        assert out["parse_summary"] == []
        assert out["hydraulic_curves"] == {}
        assert "evaluation" in out
        assert isinstance(out["evaluation"], dict)
