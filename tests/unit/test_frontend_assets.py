import json
import os


def test_package_json_structure() -> None:
    pkg_path = os.path.join(os.path.dirname(__file__), "../../web/package.json")
    assert os.path.exists(pkg_path), "web/package.json must exist"

    with open(pkg_path, encoding="utf-8") as f:
        pkg_data = json.load(f)

    assert pkg_data["name"] == "idra-web"
    deps = pkg_data.get("dependencies", {})
    assert "@tanstack/react-query" in deps
    assert "zustand" in deps
    assert "maplibre-gl" in deps
    assert "lucide-react" in deps
    assert "react" in deps


def test_vite_config_proxy_configured() -> None:
    vite_path = os.path.join(os.path.dirname(__file__), "../../web/vite.config.ts")
    assert os.path.exists(vite_path), "web/vite.config.ts must exist"

    with open(vite_path, encoding="utf-8") as f:
        content = f.read()

    assert "/api" in content
    assert "5173" in content


def test_study_area_bbox_constants() -> None:
    map_container_path = os.path.join(
        os.path.dirname(__file__), "../../web/src/components/map/MapContainer.tsx"
    )
    assert os.path.exists(map_container_path), "MapContainer.tsx must exist"

    with open(map_container_path, encoding="utf-8") as f:
        content = f.read()

    # Verify Chennai Core BBox coordinates in map component
    assert "80.15" in content
    assert "12.95" in content
    assert "80.30" in content
    assert "13.15" in content


def test_m12_ui_components_present() -> None:
    base_dir = os.path.join(os.path.dirname(__file__), "../../web/src/components")
    expected_files = [
        "briefing/OriginBadge.tsx",
        "briefing/ProvenanceTag.tsx",
        "briefing/VerificationControls.tsx",
        "briefing/RecommendationCard.tsx",
        "briefing/BriefingPanel.tsx",
        "runs/RunTimeline.tsx",
        "assistant/CitizenChatDrawer.tsx",
    ]
    for rel_path in expected_files:
        full_path = os.path.join(base_dir, rel_path)
        assert os.path.exists(full_path), f"Missing M12 component: {rel_path}"

    header_path = os.path.join(base_dir, "layout/Header.tsx")
    with open(header_path, encoding="utf-8") as f:
        header_content = f.read()
    assert "DISCLAIMER:" in header_content
    assert "112" in header_content
