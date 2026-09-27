import pytest
import numpy as np
from direct.showbase.ShowBase import ShowBase
from panda3d.core import GeomVertexReader, RenderModeAttrib, loadPrcFileData

from gesture_control.core.models import HandSide
from hand_modeling_demo.config import Settings
from hand_modeling_demo.domain import InteractionMode, PrimitiveKind, Vec2, Vec3
from hand_modeling_demo.gestures.pointers import PointerState
from hand_modeling_demo.model.entities import MeshEntity, ModelStore, Transform, create_primitive
from hand_modeling_demo.rendering.scene import HighlightRole, PandaScene
from hand_modeling_demo.rendering.mesh_bridge import mesh_to_geom_node


@pytest.fixture(scope="module")
def panda_base():
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\nnotify-level warning")
    base = ShowBase(windowType="offscreen")
    yield base
    base.destroy()


@pytest.fixture
def scene(panda_base):
    item = PandaScene(panda_base, Settings(), viewport_size=(800, 600))
    yield item
    item.close()


def entity(entity_id: str, position: Vec3) -> MeshEntity:
    return MeshEntity(
        entity_id,
        PrimitiveKind.CUBE,
        create_primitive(PrimitiveKind.CUBE),
        Transform(position),
    )


def test_sync_creates_and_removes_one_node_per_entity(scene: PandaScene) -> None:
    store = ModelStore()
    store.add(entity("a", Vec3(0.0, 0.0, 0.0)))
    scene.sync(store)
    assert scene.entity_ids == ("a",)

    store.clear()
    scene.sync(store)

    assert scene.entity_ids == ()


def test_pick_returns_nearest_entity(scene: PandaScene) -> None:
    store = ModelStore()
    store.add(entity("front", Vec3(0.0, -1.0, 0.0)))
    store.add(entity("back", Vec3(0.0, 1.0, 0.0)))
    scene.sync(store)

    hit = scene.pick(Vec2(0.5, 0.5))

    assert hit is not None
    assert hit.entity_id == "front"


def test_pan_moves_camera_opposite_hand_delta(scene: PandaScene) -> None:
    before = scene.camera_position

    scene.pan(Vec2(0.1, -0.2))

    assert scene.camera_position.x < before.x
    assert scene.camera_position.z > before.z


def test_pan_scale_tracks_camera_distance(scene: PandaScene) -> None:
    scene._distance = 12.0
    scene._focus = Vec3(0.0, 0.0, 0.0)
    scene._apply_camera()
    scene.pan(Vec2(0.1, 0.0))
    far_amount = abs(scene.focus_point.x)

    scene._distance = 6.0
    scene._focus = Vec3(0.0, 0.0, 0.0)
    scene._apply_camera()
    scene.pan(Vec2(0.1, 0.0))
    near_amount = abs(scene.focus_point.x)

    assert near_amount == pytest.approx(far_amount / 2.0)


def test_zoom_changes_distance_by_a_consistent_ratio(scene: PandaScene) -> None:
    scene._distance = 12.0
    scene.zoom(0.1)
    far_ratio = scene.distance / 12.0

    scene._distance = 6.0
    scene.zoom(0.1)
    near_ratio = scene.distance / 6.0

    assert near_ratio == pytest.approx(far_ratio)


def test_zoom_and_orbit_are_bounded(scene: PandaScene) -> None:
    before_distance, before_yaw = scene.distance, scene.yaw
    scene.zoom(1.0)
    scene.orbit(Vec2(1.0, 0.0))
    assert scene.distance < before_distance
    assert scene.yaw > before_yaw

    for _ in range(1000):
        scene.zoom(1.0)
        scene.orbit(Vec2(0.0, 1.0))

    assert scene.min_distance <= scene.distance <= scene.max_distance
    assert -85.0 <= scene.pitch <= 85.0


def test_screen_center_intersects_camera_facing_plane(scene: PandaScene) -> None:
    point = scene.screen_plane_point(Vec2(0.5, 0.5), depth=scene.distance)

    assert point.x == pytest.approx(scene.focus_point.x, abs=1e-5)
    assert point.y == pytest.approx(scene.focus_point.y, abs=1e-5)
    assert point.z == pytest.approx(scene.focus_point.z, abs=1e-5)
    assert scene.depth_of(point) == pytest.approx(scene.distance)


def test_resize_viewport_updates_camera_aspect_ratio(scene: PandaScene) -> None:
    scene.resize_viewport(1920, 1080)

    assert scene.viewport_size == (1920, 1080)
    assert scene.base.camLens.getAspectRatio() == pytest.approx(16 / 9)


def test_highlight_roles_and_control_points_are_stateful(scene: PandaScene) -> None:
    store = ModelStore()
    store.add(entity("a", Vec3(0.0, 0.0, 0.0)))
    scene.sync(store)
    scene.set_highlights({HandSide.LEFT: "a"})
    assert scene.highlight_for("a") is HighlightRole.LEFT
    assert scene._outline_nodes["a"].isHidden() is False
    assert scene._nodes["a"].getRenderMode() != RenderModeAttrib.MWireframe

    scene.show_union_failure(("a",))
    assert scene.highlight_for("a") is HighlightRole.ERROR

    scene.set_pointers(
        {HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.25, 0.75), False, 10)}
    )
    assert scene.visible_pointer_sides == (HandSide.RIGHT,)


def test_outline_uses_fixed_pixel_shader_across_model_scales(scene: PandaScene) -> None:
    store = ModelStore()
    item = entity("fixed-outline", Vec3(0.0, 0.0, 0.0))
    store.add(item)
    scene.sync(store)
    outline = scene._outline_nodes["fixed-outline"]

    assert tuple(outline.getScale()) == pytest.approx((1.0, 1.0, 1.0))
    assert outline.getShaderInput("outline_width_pixels").getVector().x == pytest.approx(3.0)

    store.replace(item.with_transform(scale=4.0))
    scene.sync(store)

    assert tuple(outline.getScale()) == pytest.approx((1.0, 1.0, 1.0))
    assert outline.getShaderInput("outline_width_pixels").getVector().x == pytest.approx(3.0)


def test_outline_pixel_shader_tracks_viewport_size(scene: PandaScene) -> None:
    store = ModelStore()
    store.add(entity("viewport-outline", Vec3(0.0, 0.0, 0.0)))
    scene.sync(store)
    outline = scene._outline_nodes["viewport-outline"]

    scene.resize_viewport(2560, 1440)

    viewport = outline.getShaderInput("outline_viewport")
    assert tuple(viewport.getVector())[:2] == pytest.approx((2560.0, 1440.0))


def test_rendered_outline_stays_three_pixels_when_model_scale_changes(
    scene: PandaScene,
) -> None:
    store = ModelStore()
    item = entity("pixel-proof", Vec3(0.0, 0.0, 0.0))
    store.add(item)

    def rendered_margin(
        scale: float, *, camera_distance: float = 12.0
    ) -> tuple[int, int, int, int]:
        scene._distance = camera_distance
        scene._apply_camera()
        store.replace(item.with_transform(scale=scale))
        scene.sync(store)
        scene.set_highlights({HandSide.LEFT: "pixel-proof"})
        scene.base.graphicsEngine.renderFrame()
        scene.base.graphicsEngine.renderFrame()
        width = scene.base.win.getXSize()
        height = scene.base.win.getYSize()
        pixels = np.frombuffer(
            scene.base.win.getScreenshot().getRamImageAs("RGB"), dtype=np.uint8
        ).reshape(height, width, 3)
        red, green, blue = (pixels[:, :, channel] for channel in range(3))
        outline = (red < 100) & (green > 120) & (blue > 180)
        model = (red > 40) & (green > 40) & (blue > 40) & ~outline
        outline_y, outline_x = np.where(outline)
        model_y, model_x = np.where(model)
        assert outline_x.size > 0
        assert model_x.size > 0
        return (
            int(model_x.min() - outline_x.min()),
            int(outline_x.max() - model_x.max()),
            int(model_y.min() - outline_y.min()),
            int(outline_y.max() - model_y.max()),
        )

    small_margin = rendered_margin(0.75)
    large_margin = rendered_margin(2.0)
    near_margin = rendered_margin(1.0, camera_distance=6.0)
    far_margin = rendered_margin(1.0, camera_distance=18.0)

    assert small_margin == pytest.approx((3, 3, 3, 3), abs=1)
    assert large_margin == pytest.approx((3, 3, 3, 3), abs=1)
    assert near_margin == pytest.approx((3, 3, 3, 3), abs=1)
    assert far_margin == pytest.approx((3, 3, 3, 3), abs=1)


def test_pointer_visual_uses_full_widescreen_width(scene: PandaScene) -> None:
    scene.resize_viewport(1920, 1080)
    scene.set_pointers(
        {HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(1.0, 0.5), False, 10)}
    )
    pointer = scene._pointer_nodes[HandSide.RIGHT]
    assert pointer.getX() == pytest.approx(16 / 9)


def test_camera_gesture_replaces_two_pointers_with_open_hand_at_midpoint(
    scene: PandaScene,
) -> None:
    pointers = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.2, 0.4), False, 10),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.8, 0.6), False, 10),
    }
    scene.set_pointers(pointers)

    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, pointers)

    assert scene.camera_gesture_visible is True
    assert all(node.isHidden() for node in scene._pointer_nodes.values())
    assert scene._camera_gesture_node.getX() == pytest.approx(0.0)
    assert scene._camera_gesture_node.getZ() == pytest.approx(0.0)

    scene.set_camera_gesture(InteractionMode.NEUTRAL, pointers)
    assert scene.camera_gesture_visible is False
    assert all(not node.isHidden() for node in scene._pointer_nodes.values())


def test_visible_camera_gesture_motion_directly_moves_render_camera(
    scene: PandaScene,
) -> None:
    start = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.2, 0.4), False, 10),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.8, 0.6), False, 10),
    }
    moved = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.3, 0.4), False, 20),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.9, 0.6), False, 20),
    }
    before = scene.camera_position
    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, start)

    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, moved)

    assert scene.camera_gesture_visible is True
    assert scene.camera_position != before


def test_camera_freeze_discards_transition_motion_and_rebases_on_resume(
    scene: PandaScene,
) -> None:
    def hands(x: float, y: float):
        return {
            HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(x, 0.4), False, 10),
            HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(y, 0.6), False, 10),
        }

    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, hands(0.2, 0.8))
    before = scene.camera_position
    scene.set_camera_gesture(
        InteractionMode.CAMERA_PAN, hands(0.3, 0.9), motion_enabled=False
    )
    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, hands(0.4, 1.0))
    assert scene.camera_position == before
    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, hands(0.5, 1.0))
    assert scene.camera_position != before


def test_visible_zoom_gesture_directly_moves_render_camera(
    scene: PandaScene,
) -> None:
    zoom_start = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.3, 0.5), False, 10),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.7, 0.5), False, 10),
    }
    zoom_moved = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.2, 0.5), False, 20),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.8, 0.5), False, 20),
    }
    before_distance = scene.distance
    scene.set_camera_gesture(InteractionMode.CAMERA_ZOOM, zoom_start)
    scene.set_camera_gesture(InteractionMode.CAMERA_ZOOM, zoom_moved)
    assert scene.distance < before_distance


def test_orbit_gesture_horizontal_and_vertical_directions_are_independent(
    scene: PandaScene,
) -> None:
    horizontal_start = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.5, 0.5), False, 30),
    }
    moved_right = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.7, 0.5), False, 40),
    }
    before_yaw, before_pitch = scene.yaw, scene.pitch
    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, horizontal_start)
    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, moved_right)

    assert scene.yaw > before_yaw
    assert scene.pitch == pytest.approx(before_pitch)

    scene.set_camera_gesture(InteractionMode.NEUTRAL, {})
    vertical_start = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.5, 0.5), False, 30),
    }
    moved_up = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.5, 0.3), False, 40),
    }
    before_yaw, before_pitch = scene.yaw, scene.pitch
    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, vertical_start)
    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, moved_up)

    assert scene.yaw == pytest.approx(before_yaw)
    assert scene.pitch < before_pitch


def test_orbit_gesture_suppresses_small_cross_axis_drift(scene: PandaScene) -> None:
    start = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.5, 0.5), False, 10),
    }
    mostly_right = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.7, 0.53), False, 20),
    }
    before_pitch = scene.pitch
    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, start)

    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, mostly_right)

    assert scene.pitch == pytest.approx(before_pitch)


def test_pan_gesture_uses_the_same_screen_axis_conversion(scene: PandaScene) -> None:
    start = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.2, 0.5), False, 10),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.8, 0.5), False, 10),
    }
    moved_up = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.2, 0.3), False, 20),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.8, 0.3), False, 20),
    }
    before = scene.focus_point
    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, start)

    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, moved_up)

    assert scene.focus_point.z < before.z


def test_direct_camera_gesture_clamps_spikes_and_has_no_drift(
    scene: PandaScene,
) -> None:
    start = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.1, 0.5), False, 10),
    }
    spike = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.9, 0.5), False, 20),
    }
    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, start)
    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, spike)
    after_spike = scene.yaw

    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, spike)

    assert after_spike == pytest.approx(0.06 * scene.settings.orbit_gain)
    assert scene.yaw == pytest.approx(after_spike)


def test_visible_pan_gesture_changes_the_final_model_pixels(
    scene: PandaScene,
) -> None:
    store = ModelStore()
    store.add(entity("camera-proof", Vec3(0.0, 0.0, 0.0)))
    scene.sync(store)
    start = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.2, 0.5), False, 10),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.8, 0.5), False, 10),
    }
    moved = {
        HandSide.LEFT: PointerState(HandSide.LEFT, Vec2(0.35, 0.5), False, 20),
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.95, 0.5), False, 20),
    }
    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, start)
    scene._camera_gesture_node.hide()
    scene.base.graphicsEngine.renderFrame()
    scene.base.graphicsEngine.renderFrame()
    before = np.frombuffer(
        scene.base.win.getScreenshot().getRamImageAs("RGB"), dtype=np.uint8
    ).copy()

    scene.set_camera_gesture(InteractionMode.CAMERA_PAN, moved)
    scene._camera_gesture_node.hide()
    scene.base.graphicsEngine.renderFrame()
    scene.base.graphicsEngine.renderFrame()
    after = np.frombuffer(
        scene.base.win.getScreenshot().getRamImageAs("RGB"), dtype=np.uint8
    ).copy()

    assert np.count_nonzero(before != after) > 100


def test_orbit_gesture_uses_right_pointer_when_it_is_the_only_hand(
    scene: PandaScene,
) -> None:
    pointers = {
        HandSide.RIGHT: PointerState(HandSide.RIGHT, Vec2(0.75, 0.25), False, 10),
    }
    scene.set_pointers(pointers)

    scene.set_camera_gesture(InteractionMode.CAMERA_ORBIT, pointers)

    assert scene.camera_gesture_visible is True
    assert scene._camera_gesture_node.getX() == pytest.approx(0.5 * scene.base.camLens.getAspectRatio())
    assert scene._camera_gesture_node.getZ() == pytest.approx(0.5)


def test_render_mesh_preserves_sharp_cube_edges() -> None:
    mesh = create_primitive(PrimitiveKind.CUBE)
    node = mesh_to_geom_node(mesh, "cube")
    data = node.getGeom(0).getVertexData()
    reader = GeomVertexReader(data, "normal")
    normals = set()
    while not reader.isAtEnd():
        normal = reader.getData3f()
        normals.add(tuple(round(float(value), 3) for value in normal))

    assert data.getNumRows() == len(mesh.faces) * 3
    assert normals == {
        (-1.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, -1.0),
        (0.0, 0.0, 1.0),
    }

def test_pick_uses_pixel_tolerance_after_center_ray_misses(
    scene: PandaScene, monkeypatch: pytest.MonkeyPatch
) -> None:
    sampled: list[Vec2] = []

    def fake_pick_exact(pointer: Vec2):
        sampled.append(pointer)
        if pointer.x > 0.5:
            from hand_modeling_demo.rendering.scene import PickResult

            return PickResult("a", Vec3(0.0, 0.0, 0.0), Vec3(0.0, -1.0, 0.0), 2.0)
        return None

    monkeypatch.setattr(scene, "_pick_exact", fake_pick_exact)

    hit = scene.pick(Vec2(0.5, 0.5))

    assert hit is not None
    assert hit.entity_id == "a"
    assert sampled[0] == Vec2(0.5, 0.5)
    assert any(pointer.x > 0.5 for pointer in sampled[1:])


def test_union_failure_remains_red_while_either_pointer_still_hovers(
    scene: PandaScene,
) -> None:
    store = ModelStore()
    store.add(entity("a", Vec3(0.0, 0.0, 0.0)))
    scene.sync(store)
    scene.show_union_failure(("a",))

    scene.set_highlights({HandSide.LEFT: "a", HandSide.RIGHT: None})

    assert scene.highlight_for("a") is HighlightRole.ERROR

    scene.set_highlights({HandSide.LEFT: None, HandSide.RIGHT: None})
    assert scene.highlight_for("a") is HighlightRole.NONE


def test_creation_preview_is_separate_from_committed_entity_nodes(scene: PandaScene) -> None:
    class Preview:
        kind = PrimitiveKind.SPHERE
        world_center = Vec3(1.0, 2.0, 3.0)
        scale = 0.2

    scene.set_preview(Preview())
    assert scene.has_preview is True
    assert scene.entity_ids == ()

    scene.set_preview(None)
    assert scene.has_preview is False
