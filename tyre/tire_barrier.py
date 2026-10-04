"""Bariéra z pneumatik jako Geometry Nodes modifikátor.

Stejný způsob použití jako TREES ve TrackTools: jednou spusť skript,
potom na křivku přidej modifikátor TireBarrier (Add Modifier),
nebo ho přetáhni z Asset Browseru (Current File).

Stoh pneumatik se rozloží podél křivky. Rozestup je Distance,
stranu řeší Offset.
"""

from __future__ import annotations

import math
import os
import sys

import bpy

GROUP_NAME = "Tire Barrier"
MODIFIER_NAME = "Tire Barrier"
FBX_NAME = "tyre.fbx"
SOURCE_FLAG = "tire_barrier_source"
SOURCE_COLLECTION = "TireBarrier_Source"
ASSET_BLEND = "TireBarrier.blend"
CATALOG_ID = "7c1e4a92-6d08-4f3b-a1e5-9b2d84c0f6aa"
CATALOG_PATH = "Modifiers"

DEFAULTS = {
    "Distance": 0.7,
    "Offset": 0.0,
    "Snap Distance": 100.0,
    "Count": 5,
    "Tire Height": 0.15,
    "Jitter Amount": 0.05,
    "Top Tire Offset": 0.08,
    "Top Tire Tilt": math.radians(11.5),
    "Seed": 0,
    "Realize Instances": True,
}


def _script_dirs():
    dirs = []
    if "__file__" in globals():
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    space = getattr(bpy.context, "space_data", None)
    text = getattr(space, "text", None)
    if text is not None and text.filepath:
        dirs.append(os.path.dirname(bpy.path.abspath(text.filepath)))
    if bpy.data.filepath:
        dirs.append(os.path.dirname(bpy.path.abspath(bpy.data.filepath)))
    dirs.append(os.getcwd())
    unique = []
    for path in dirs:
        if path and path not in unique:
            unique.append(path)
    return unique


def _shallow_find(root, name, max_depth=4):
    if not root or not os.path.isdir(root):
        return None
    root = os.path.abspath(root)
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) - base_depth
        if depth >= max_depth:
            dirnames.clear()
            continue
        if name in filenames:
            return os.path.join(dirpath, name)
    return None


def resolve_fbx_path():
    relatives = (
        FBX_NAME,
        os.path.join("tyre", FBX_NAME),
        os.path.join("tyre", "tyre", FBX_NAME),
    )
    searched = []
    for folder in _script_dirs():
        if not folder or not os.path.isdir(folder):
            searched.append(os.path.join(folder or "", FBX_NAME))
            continue
        for relative in relatives:
            candidate = os.path.join(folder, relative)
            searched.append(candidate)
            if os.path.isfile(candidate):
                return candidate
        found = _shallow_find(folder, FBX_NAME)
        if found:
            return found
    raise FileNotFoundError(
        "Soubor tyre.fbx nebyl nalezen. Hledáno v:\n" + "\n".join(searched)
    )


def enter_object_mode():
    if bpy.context.mode == "OBJECT":
        return
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")


def import_fbx_objects(path):
    before = set(bpy.data.objects)
    enter_object_mode()
    errors = []
    operators = []
    if hasattr(bpy.ops, "wm") and hasattr(bpy.ops.wm, "fbx_import"):
        operators.append(lambda: bpy.ops.wm.fbx_import(filepath=path))
    if hasattr(bpy.ops, "import_scene") and hasattr(bpy.ops.import_scene, "fbx"):
        operators.append(lambda: bpy.ops.import_scene.fbx(filepath=path))
    if not operators:
        raise RuntimeError("V tomhle Blenderu není FBX import (wm.fbx_import ani import_scene.fbx).")

    finished = False
    for op in operators:
        try:
            result = op()
        except (AttributeError, RuntimeError, TypeError) as exc:
            errors.append(str(exc))
            continue
        if result is None or "FINISHED" in result:
            finished = True
            break
        errors.append(str(result))
    if not finished:
        raise RuntimeError("Import FBX selhal: " + "; ".join(errors))

    imported = [obj for obj in bpy.data.objects if obj not in before]
    if not imported:
        imported = list(bpy.context.selected_objects)
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"{path} neobsahuje žádný mesh.")
    meshes.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
    for obj in imported:
        obj[SOURCE_FLAG] = True
    return meshes[0], imported


def source_collection():
    collection = bpy.data.collections.get(SOURCE_COLLECTION)
    if collection is None:
        collection = bpy.data.collections.new(SOURCE_COLLECTION)
    scene_root = bpy.context.scene.collection
    if collection.name not in scene_root.children:
        scene_root.children.link(collection)
    return collection


def move_to_collection(obj, collection):
    for owner in list(obj.users_collection):
        if owner != collection:
            owner.objects.unlink(obj)
    if obj.name not in collection.objects:
        collection.objects.link(obj)


def stash_source(obj):
    """Schová zdroj ve viewportu, ale nechá ho ve vyhodnocení depsgraphu.

    ``hide_render`` / ``hide_viewport`` by Object Info v renderu vyprázdnily.
    Vypnutá viditelnost pro paprsky zdroj v kameře neschová jako druhou pneumatiku.
    """
    move_to_collection(obj, source_collection())
    obj.hide_select = True
    for attr in (
        "visible_camera",
        "visible_diffuse",
        "visible_glossy",
        "visible_transmission",
        "visible_volume_scatter",
        "visible_shadow",
    ):
        if hasattr(obj, attr):
            setattr(obj, attr, False)
    obj[SOURCE_FLAG] = True
    try:
        obj.hide_set(True)
    except RuntimeError:
        pass


def existing_tire():
    found = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.get(SOURCE_FLAG) and obj.data is not None
    ]
    if not found:
        return None
    found.sort(key=lambda obj: len(obj.data.vertices), reverse=True)
    return found[0]


def ensure_tire_object():
    path = resolve_fbx_path()
    mtime = os.path.getmtime(path)
    current = existing_tire()
    if current is not None and abs(float(current.get("tire_barrier_fbx_mtime", -1.0)) - mtime) < 1.0:
        return current

    tire, imported = import_fbx_objects(path)
    imported_ids = {obj.as_pointer() for obj in imported}
    for obj in imported:
        obj["tire_barrier_fbx_mtime"] = mtime
        stash_source(obj)

    for obj in list(bpy.data.objects):
        if not obj.get(SOURCE_FLAG) or obj.as_pointer() in imported_ids:
            continue
        mesh = obj.data if obj.type == "MESH" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    return tire


def create_carrier():
    curve = bpy.data.curves.new(GROUP_NAME, type="CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
    spline.points[1].co = (8.0, 0.0, 0.0, 1.0)
    obj = bpy.data.objects.new(GROUP_NAME, curve)
    bpy.context.collection.objects.link(obj)
    obj.location = bpy.context.scene.cursor.location
    return obj


def pick_target(source, previous_active, previous_selected):
    if (
        previous_active is not None
        and previous_active.type in {"CURVE", "MESH"}
        and previous_active in previous_selected
        and previous_active is not source
        and not previous_active.get(SOURCE_FLAG)
    ):
        return previous_active
    return create_carrier()


def choose_socket_type(ng, candidates):
    validate = getattr(ng, "valid_socket_type", None)
    if validate is None:
        return candidates[0]
    for candidate in candidates:
        try:
            if validate(candidate):
                return candidate
        except (TypeError, ValueError):
            continue
    return candidates[-1]


def new_interface_socket(ng, name, socket_type, in_out, description="", parent=None):
    kwargs = {"name": name, "in_out": in_out, "socket_type": socket_type}
    if parent is not None:
        kwargs["parent"] = parent
    try:
        return ng.interface.new_socket(description=description, **kwargs)
    except TypeError as exc:
        message = str(exc)
        if parent is not None and "parent" in message:
            kwargs.pop("parent", None)
        if "description" in message:
            socket = ng.interface.new_socket(**kwargs)
            if description and hasattr(socket, "description"):
                socket.description = description
            if parent is not None and hasattr(ng.interface, "move_to_parent"):
                ng.interface.move_to_parent(socket, parent, len(parent.interface_items) if hasattr(parent, "interface_items") else 0)
            return socket
        raise


def expose_picker(socket):
    if hasattr(socket, "force_non_field"):
        socket.force_non_field = True
    if hasattr(socket, "hide_in_modifier"):
        socket.hide_in_modifier = False
    if hasattr(socket, "structure_type"):
        try:
            socket.structure_type = "SINGLE"
        except TypeError:
            pass


def add_float_input(ng, name, default, description, minimum=0.0, kind="distance"):
    if kind == "angle":
        candidates = ("NodeSocketFloatAngle", "NodeSocketFloat")
        subtype = "ANGLE"
    elif kind == "distance":
        candidates = ("NodeSocketFloatDistance", "NodeSocketFloat")
        subtype = "DISTANCE"
    else:
        candidates = ("NodeSocketFloat",)
        subtype = None
    socket = None
    socket_type = None
    errors = []
    for candidate in candidates:
        try:
            socket = new_interface_socket(ng, name, candidate, "INPUT", description)
            socket_type = candidate
            break
        except TypeError as exc:
            errors.append(str(exc))
    if socket is None:
        raise TypeError(f"Socket {name} se nepodařilo vytvořit: {errors[-1] if errors else ''}")
    if socket_type == "NodeSocketFloat" and subtype and hasattr(socket, "subtype"):
        socket.subtype = subtype
    socket.default_value = default
    if minimum is not None and hasattr(socket, "min_value"):
        socket.min_value = minimum
    return socket


def add_node(nodes, bl_idname, x, y, label=None):
    node = nodes.new(bl_idname)
    node.location = (x, y)
    if label:
        node.label = label
        node.name = label
    return node


def sock(node, collection, name):
    sockets = getattr(node, collection)
    for socket in sockets:
        if socket.name == name:
            return socket
    available = ", ".join(socket.name for socket in sockets) or "(žádné)"
    label = node.label or node.name
    raise KeyError(
        f"Uzel {node.bl_idname} „{label}“ nemá {collection}.{name}. Dostupné: {available}"
    )


def connect(links, src_node, src_name, dst_node, dst_name):
    links.new(sock(src_node, "outputs", src_name), sock(dst_node, "inputs", dst_name))


def rebuild_group():
    previous = bpy.data.node_groups.get(GROUP_NAME)
    if previous is not None and previous.bl_idname != "GeometryNodeTree":
        bpy.data.node_groups.remove(previous)
        previous = None
    if previous is not None:
        previous.name = f"{GROUP_NAME}_old"

    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    if hasattr(ng, "is_modifier"):
        ng.is_modifier = True
    if hasattr(ng, "description"):
        ng.description = "Bariéra z pneumatik podél křivky."
    ng.use_fake_user = True
    if previous is not None:
        for obj in bpy.data.objects:
            for mod in obj.modifiers:
                if mod.type == "NODES" and mod.node_group == previous:
                    mod.node_group = ng
        bpy.data.node_groups.remove(previous)
    return ng


def build_group():
    ng = rebuild_group()
    ng.interface.clear()

    new_interface_socket(
        ng,
        "Geometry",
        "NodeSocketGeometry",
        "INPUT",
        "Použije se jen když není vybraná křivka.",
    )
    snap = ng.interface.new_panel(
        "Snap",
        description="Křivka a terén, na které se bariéra připne.",
        default_closed=False,
    )
    curve = new_interface_socket(
        ng,
        "Curve",
        choose_socket_type(ng, ("NodeSocketObject",)),
        "INPUT",
        "Křivka, podél které se bariéra rozloží.",
        parent=snap,
    )
    terrain = new_interface_socket(
        ng,
        "Terrain",
        choose_socket_type(ng, ("NodeSocketObject",)),
        "INPUT",
        "Mesh terénu, na který se stohy připnou.",
        parent=snap,
    )
    expose_picker(curve)
    expose_picker(terrain)
    tire = new_interface_socket(
        ng,
        "Tire Object",
        choose_socket_type(ng, ("NodeSocketObject",)),
        "INPUT",
        "Mesh pneumatiky, který se instancuje. Stejná role jako Instance Object u stromů.",
    )
    expose_picker(tire)
    add_float_input(
        ng,
        "Distance",
        DEFAULTS["Distance"],
        "Rozestup stohů podél křivky.",
        minimum=0.01,
    )
    add_float_input(
        ng,
        "Offset",
        DEFAULTS["Offset"],
        "Posun do strany od křivky. Záporná hodnota dá bariéru na druhou stranu.",
        minimum=None,
    )
    add_float_input(
        ng,
        "Snap Distance",
        DEFAULTS["Snap Distance"],
        "Jak vysoko nad křivkou začíná paprsek na terén. Paprsek jde dolů o dvojnásobek.",
        minimum=0.01,
    )
    count = new_interface_socket(
        ng,
        "Count",
        choose_socket_type(ng, ("NodeSocketInt",)),
        "INPUT",
        "Počet pneumatik v jednom stohu.",
    )
    count.default_value = DEFAULTS["Count"]
    if hasattr(count, "min_value"):
        count.min_value = 1

    add_float_input(
        ng,
        "Tire Height",
        DEFAULTS["Tire Height"],
        "Svislý rozestup vrstev.",
        minimum=0.01,
    )
    add_float_input(
        ng,
        "Jitter Amount",
        DEFAULTS["Jitter Amount"],
        "Náhodný posun běžných pneumatik v XY.",
    )
    add_float_input(
        ng,
        "Top Tire Offset",
        DEFAULTS["Top Tire Offset"],
        "Posun vrchní pneumatiky v náhodném směru XY.",
    )
    add_float_input(
        ng,
        "Top Tire Tilt",
        DEFAULTS["Top Tire Tilt"],
        "Náklon vrchní pneumatiky ve směru posunu, v radiánech.",
        minimum=None,
        kind="angle",
    )
    seed = new_interface_socket(
        ng,
        "Seed",
        choose_socket_type(ng, ("NodeSocketInt",)),
        "INPUT",
        "Posun náhody, stejný význam jako Seed u stromů.",
    )
    seed.default_value = DEFAULTS["Seed"]
    if hasattr(seed, "min_value"):
        seed.min_value = 0
    realize_input = new_interface_socket(
        ng,
        "Realize Instances",
        choose_socket_type(ng, ("NodeSocketBool",)),
        "INPUT",
        "Sloučí bariéru do jednoho meshe. Pro uložení toho, co je ve viewportu, "
        "nech zapnuté a použij Object → Convert → Mesh.",
    )
    realize_input.default_value = DEFAULTS["Realize Instances"]
    new_interface_socket(ng, "Geometry", "NodeSocketGeometry", "OUTPUT")

    nodes = ng.nodes
    links = ng.links

    group_in = add_node(nodes, "NodeGroupInput", -1680, 80, "Group Input")
    group_in.width = 200
    group_out = add_node(nodes, "NodeGroupOutput", 2320, 360, "Group Output")
    group_out.is_active_output = True

    obj_info = add_node(nodes, "GeometryNodeObjectInfo", -1380, 460, "Tire Object")
    obj_info.transform_space = "RELATIVE"
    if "As Instance" in obj_info.inputs:
        obj_info.inputs["As Instance"].default_value = False
    connect(links, group_in, "Tire Object", obj_info, "Object")

    # Relative drží i vzájemný posun objektů ve scéně. Ten se odečte,
    # aby stoh seděl na bodech nosiče; rotace a měřítko assetu zůstanou.
    recenter = add_node(nodes, "ShaderNodeVectorMath", -1120, 280, "Inverse Offset")
    recenter.operation = "SCALE"
    connect(links, obj_info, "Location", recenter, "Vector")
    sock(recenter, "inputs", "Scale").default_value = -1.0

    centered = add_node(nodes, "GeometryNodeSetPosition", -880, 460, "Center On Carrier")
    connect(links, obj_info, "Geometry", centered, "Geometry")
    connect(links, recenter, "Vector", centered, "Offset")

    bounds = add_node(nodes, "GeometryNodeBoundBox", -620, 460, "Tire Bounds")
    connect(links, centered, "Geometry", bounds, "Geometry")
    bounds_min = add_node(nodes, "ShaderNodeSeparateXYZ", -400, 320, "Tire Min")
    connect(links, bounds, "Min", bounds_min, "Vector")

    height = add_node(nodes, "ShaderNodeCombineXYZ", -1120, 680, "Layer Offset")
    height.inputs["X"].default_value = 0.0
    height.inputs["Y"].default_value = 0.0
    connect(links, group_in, "Tire Height", height, "Z")

    line = add_node(nodes, "GeometryNodeMeshLine", -860, 700, "Stack Points")
    line.mode = "OFFSET"
    line.count_mode = "TOTAL"
    connect(links, group_in, "Count", line, "Count")
    connect(links, height, "Vector", line, "Offset")

    mesh_to_curve = add_node(nodes, "GeometryNodeMeshToCurve", -1560, 980, "Mesh to Curve")
    connect(links, group_in, "Geometry", mesh_to_curve, "Mesh")
    joined = add_node(nodes, "GeometryNodeJoinGeometry", -1320, 900, "Curve or Mesh")
    links.new(sock(mesh_to_curve, "outputs", "Curve"), sock(joined, "inputs", "Geometry"))
    links.new(sock(group_in, "outputs", "Geometry"), sock(joined, "inputs", "Geometry"))

    curve_info = add_node(nodes, "GeometryNodeObjectInfo", -1560, 1240, "Curve Object")
    curve_info.transform_space = "RELATIVE"
    if "As Instance" in curve_info.inputs:
        curve_info.inputs["As Instance"].default_value = False
    connect(links, group_in, "Curve", curve_info, "Object")
    curve_mesh = add_node(nodes, "GeometryNodeMeshToCurve", -1320, 1320, "Curve Mesh")
    connect(links, curve_info, "Geometry", curve_mesh, "Mesh")
    curve_joined = add_node(nodes, "GeometryNodeJoinGeometry", -1100, 1240, "Chosen Curve")
    links.new(sock(curve_mesh, "outputs", "Curve"), sock(curve_joined, "inputs", "Geometry"))
    links.new(sock(curve_info, "outputs", "Geometry"), sock(curve_joined, "inputs", "Geometry"))

    curve_size = add_node(nodes, "GeometryNodeAttributeDomainSize", -880, 1240, "Curve Size")
    curve_size.component = "CURVE"
    connect(links, curve_joined, "Geometry", curve_size, "Geometry")
    has_curve = add_node(nodes, "FunctionNodeCompare", -660, 1240, "Has Curve")
    has_curve.data_type = "INT"
    has_curve.operation = "GREATER_THAN"
    connect(links, curve_size, "Spline Count", has_curve, "A")
    has_curve.inputs["B"].default_value = 0

    path = add_node(nodes, "GeometryNodeSwitch", -420, 980, "Curve Source")
    path.input_type = "GEOMETRY"
    connect(links, has_curve, "Result", path, "Switch")
    connect(links, joined, "Geometry", path, "False")
    connect(links, curve_joined, "Geometry", path, "True")

    along = add_node(nodes, "GeometryNodeCurveToPoints", -180, 900, "Along Curve")
    along.mode = "LENGTH"
    connect(links, path, "Output", along, "Curve")
    connect(links, group_in, "Distance", along, "Length")

    up = add_node(nodes, "ShaderNodeCombineXYZ", -1080, 1140, "Up")
    up.inputs["X"].default_value = 0.0
    up.inputs["Y"].default_value = 0.0
    up.inputs["Z"].default_value = 1.0
    side = add_node(nodes, "ShaderNodeVectorMath", -840, 1100, "Side")
    side.operation = "CROSS_PRODUCT"
    connect(links, along, "Tangent", side, "Vector")
    links.new(sock(up, "outputs", "Vector"), side.inputs[1])
    side_n = add_node(nodes, "ShaderNodeVectorMath", -620, 1100, "Side Normal")
    side_n.operation = "NORMALIZE"
    connect(links, side, "Vector", side_n, "Vector")
    side_off = add_node(nodes, "ShaderNodeVectorMath", -400, 1100, "Side Offset")
    side_off.operation = "SCALE"
    connect(links, side_n, "Vector", side_off, "Vector")
    connect(links, group_in, "Offset", side_off, "Scale")

    placed = add_node(nodes, "GeometryNodeSetPosition", -160, 900, "Place Stacks")
    connect(links, along, "Points", placed, "Geometry")
    connect(links, side_off, "Vector", placed, "Offset")

    # Křivka z jiného objektu často leží v konstantní výšce nad tratí.
    # Při jejím výběru se odečte nejnižší bod, ať stoh zůstane na výšce nosiče.
    # Kopce na křivce zůstanou. Terén níž Z případně přepíše.
    curve_pos = add_node(nodes, "GeometryNodeInputPosition", 40, 760, "Curve Position")
    curve_z = add_node(nodes, "ShaderNodeSeparateXYZ", 240, 760, "Curve Z")
    connect(links, curve_pos, "Position", curve_z, "Vector")
    curve_z_stat = add_node(nodes, "GeometryNodeAttributeStatistic", 460, 760, "Curve Z Stat")
    curve_z_stat.data_type = "FLOAT"
    curve_z_stat.domain = "POINT"
    connect(links, placed, "Geometry", curve_z_stat, "Geometry")
    links.new(sock(curve_z, "outputs", "Z"), sock(curve_z_stat, "inputs", "Attribute"))
    drop_z = add_node(nodes, "ShaderNodeMath", 680, 760, "Drop Curve Z")
    drop_z.operation = "MULTIPLY"
    connect(links, curve_z_stat, "Min", drop_z, "Value")
    drop_z.inputs[1].default_value = -1.0
    anchor_switch = add_node(nodes, "GeometryNodeSwitch", 900, 760, "Anchor Flat Curve")
    anchor_switch.input_type = "FLOAT"
    connect(links, has_curve, "Result", anchor_switch, "Switch")
    anchor_switch.inputs["False"].default_value = 0.0
    connect(links, drop_z, "Value", anchor_switch, "True")
    anchor_vec = add_node(nodes, "ShaderNodeCombineXYZ", 1120, 760, "Anchor Offset")
    anchor_vec.inputs["X"].default_value = 0.0
    anchor_vec.inputs["Y"].default_value = 0.0
    connect(links, anchor_switch, "Output", anchor_vec, "Z")
    anchored = add_node(nodes, "GeometryNodeSetPosition", 1340, 900, "Keep Carrier Height")
    connect(links, placed, "Geometry", anchored, "Geometry")
    connect(links, anchor_vec, "Vector", anchored, "Offset")

    terrain_info = add_node(nodes, "GeometryNodeObjectInfo", -160, 1280, "Terrain Object")
    terrain_info.transform_space = "RELATIVE"
    if "As Instance" in terrain_info.inputs:
        terrain_info.inputs["As Instance"].default_value = False
    connect(links, group_in, "Terrain", terrain_info, "Object")

    ray_up = add_node(nodes, "ShaderNodeCombineXYZ", 80, 1460, "Ray Start Offset")
    ray_up.inputs["X"].default_value = 0.0
    ray_up.inputs["Y"].default_value = 0.0
    connect(links, group_in, "Snap Distance", ray_up, "Z")
    position = add_node(nodes, "GeometryNodeInputPosition", 80, 1280, "Position")
    ray_start = add_node(nodes, "ShaderNodeVectorMath", 320, 1360, "Ray Start")
    ray_start.operation = "ADD"
    connect(links, position, "Position", ray_start, "Vector")
    links.new(sock(ray_up, "outputs", "Vector"), ray_start.inputs[1])
    ray_dir = add_node(nodes, "ShaderNodeCombineXYZ", 320, 1540, "Ray Down")
    ray_dir.inputs["X"].default_value = 0.0
    ray_dir.inputs["Y"].default_value = 0.0
    ray_dir.inputs["Z"].default_value = -1.0
    ray_len = add_node(nodes, "ShaderNodeMath", 320, 1180, "Ray Length")
    ray_len.operation = "MULTIPLY"
    ray_len.inputs[1].default_value = 2.0
    connect(links, group_in, "Snap Distance", ray_len, "Value")

    raycast = add_node(nodes, "GeometryNodeRaycast", 560, 1280, "Snap Ray")
    connect(links, terrain_info, "Geometry", raycast, "Target Geometry")
    connect(links, ray_start, "Vector", raycast, "Source Position")
    connect(links, ray_dir, "Vector", raycast, "Ray Direction")
    links.new(ray_len.outputs[0], sock(raycast, "inputs", "Ray Length"))

    lift = add_node(nodes, "ShaderNodeMath", 1020, 1040, "Rest On Ground")
    lift.operation = "MULTIPLY"
    lift.inputs[1].default_value = -1.0
    links.new(sock(bounds_min, "outputs", "Z"), lift.inputs[0])
    lift_vec = add_node(nodes, "ShaderNodeCombineXYZ", 1220, 1100, "Ground Lift")
    lift_vec.inputs["X"].default_value = 0.0
    lift_vec.inputs["Y"].default_value = 0.0
    links.new(lift.outputs[0], lift_vec.inputs["Z"])
    rested = add_node(nodes, "ShaderNodeVectorMath", 1460, 1200, "Hit On Ground")
    rested.operation = "ADD"
    connect(links, raycast, "Hit Position", rested, "Vector")
    links.new(sock(lift_vec, "outputs", "Vector"), rested.inputs[1])

    ground_switch = add_node(nodes, "GeometryNodeSwitch", 1700, 1040, "Use Terrain Hit")
    ground_switch.input_type = "VECTOR"
    connect(links, raycast, "Is Hit", ground_switch, "Switch")
    connect(links, position, "Position", ground_switch, "False")
    connect(links, rested, "Vector", ground_switch, "True")

    snapped = add_node(nodes, "GeometryNodeSetPosition", 1940, 900, "Snap To Terrain")
    connect(links, anchored, "Geometry", snapped, "Geometry")
    connect(links, ground_switch, "Output", snapped, "Position")

    stacks = add_node(nodes, "GeometryNodeInstanceOnPoints", 2180, 860, "Stacks on Curve")
    connect(links, snapped, "Geometry", stacks, "Points")
    connect(links, line, "Mesh", stacks, "Instance")
    if "Scale" in stacks.inputs:
        stacks.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    stack_points = add_node(nodes, "GeometryNodeRealizeInstances", 400, 860, "Realize Stack Points")
    connect(links, stacks, "Instances", stack_points, "Geometry")
    if "Realize All" in stack_points.inputs:
        stack_points.inputs["Realize All"].default_value = True

    top_index = add_node(nodes, "FunctionNodeIntegerMath", -1380, -20, "Count - 1")
    top_index.operation = "SUBTRACT"
    top_index.inputs[1].default_value = 1
    connect(links, group_in, "Count", top_index, "Value")

    index = add_node(nodes, "GeometryNodeInputIndex", -1380, -180, "Index")

    layer = add_node(nodes, "FunctionNodeIntegerMath", -1100, -20, "Layer")
    modulo = "FLOORED_MODULO"
    if modulo not in {item.identifier for item in layer.bl_rna.properties["operation"].enum_items}:
        modulo = "MODULO"
    layer.operation = modulo
    links.new(sock(index, "outputs", "Index"), layer.inputs[0])
    links.new(sock(group_in, "outputs", "Count"), layer.inputs[1])

    is_top = add_node(nodes, "FunctionNodeCompare", -860, -20, "Is Top Tire")
    is_top.data_type = "INT"
    is_top.operation = "EQUAL"
    links.new(layer.outputs[0], sock(is_top, "inputs", "A"))
    links.new(top_index.outputs[0], sock(is_top, "inputs", "B"))

    neg_jitter = add_node(nodes, "ShaderNodeMath", -1380, -380, "Negative Jitter")
    neg_jitter.operation = "MULTIPLY"
    neg_jitter.inputs[1].default_value = -1.0
    connect(links, group_in, "Jitter Amount", neg_jitter, "Value")

    jitter_min = add_node(nodes, "ShaderNodeCombineXYZ", -1120, -300, "Jitter Min")
    links.new(neg_jitter.outputs[0], jitter_min.inputs["X"])
    links.new(neg_jitter.outputs[0], jitter_min.inputs["Y"])
    jitter_min.inputs["Z"].default_value = 0.0

    jitter_max = add_node(nodes, "ShaderNodeCombineXYZ", -1120, -480, "Jitter Max")
    connect(links, group_in, "Jitter Amount", jitter_max, "X")
    connect(links, group_in, "Jitter Amount", jitter_max, "Y")
    jitter_max.inputs["Z"].default_value = 0.0

    seed_jitter = add_node(nodes, "FunctionNodeIntegerMath", -1100, -560, "Seed Jitter")
    seed_jitter.operation = "ADD"
    seed_jitter.inputs[1].default_value = 1
    connect(links, group_in, "Seed", seed_jitter, "Value")
    jitter = add_node(nodes, "FunctionNodeRandomValue", -820, -380, "Stack Jitter")
    jitter.data_type = "FLOAT_VECTOR"
    links.new(seed_jitter.outputs[0], jitter.inputs["Seed"])
    connect(links, jitter_min, "Vector", jitter, "Min")
    connect(links, jitter_max, "Vector", jitter, "Max")
    connect(links, index, "Index", jitter, "ID")

    seed_spin = add_node(nodes, "FunctionNodeIntegerMath", -1100, -740, "Seed Spin")
    seed_spin.operation = "ADD"
    seed_spin.inputs[1].default_value = 2
    connect(links, group_in, "Seed", seed_spin, "Value")
    spin = add_node(nodes, "FunctionNodeRandomValue", -820, -640, "Tread Spin")
    spin.data_type = "FLOAT"
    spin.inputs["Min"].default_value = 0.0
    spin.inputs["Max"].default_value = math.tau
    links.new(seed_spin.outputs[0], spin.inputs["Seed"])
    connect(links, index, "Index", spin, "ID")

    spin_euler = add_node(nodes, "ShaderNodeCombineXYZ", -520, -640, "Spin Euler")
    spin_euler.inputs["X"].default_value = 0.0
    spin_euler.inputs["Y"].default_value = 0.0
    connect(links, spin, "Value", spin_euler, "Z")

    spin_rot = add_node(nodes, "FunctionNodeEulerToRotation", -260, -640, "Spin Rotation")
    connect(links, spin_euler, "Vector", spin_rot, "Euler")

    seed_angle = add_node(nodes, "FunctionNodeIntegerMath", -1100, -980, "Seed Direction")
    seed_angle.operation = "ADD"
    seed_angle.inputs[1].default_value = 3
    connect(links, group_in, "Seed", seed_angle, "Value")
    angle = add_node(nodes, "FunctionNodeRandomValue", -820, -920, "Top Direction")
    angle.data_type = "FLOAT"
    angle.inputs["Min"].default_value = 0.0
    angle.inputs["Max"].default_value = math.tau
    links.new(seed_angle.outputs[0], angle.inputs["Seed"])
    connect(links, index, "Index", angle, "ID")

    cos_a = add_node(nodes, "ShaderNodeMath", -560, -820, "cos")
    cos_a.operation = "COSINE"
    connect(links, angle, "Value", cos_a, "Value")
    sin_a = add_node(nodes, "ShaderNodeMath", -560, -1000, "sin")
    sin_a.operation = "SINE"
    connect(links, angle, "Value", sin_a, "Value")

    offset_x = add_node(nodes, "ShaderNodeMath", -300, -760, "Offset X")
    offset_x.operation = "MULTIPLY"
    links.new(cos_a.outputs[0], offset_x.inputs[0])
    links.new(sock(group_in, "outputs", "Top Tire Offset"), offset_x.inputs[1])

    offset_y = add_node(nodes, "ShaderNodeMath", -300, -940, "Offset Y")
    offset_y.operation = "MULTIPLY"
    links.new(sin_a.outputs[0], offset_y.inputs[0])
    links.new(sock(group_in, "outputs", "Top Tire Offset"), offset_y.inputs[1])

    top_offset = add_node(nodes, "ShaderNodeCombineXYZ", -40, -840, "Top Offset")
    links.new(offset_x.outputs[0], top_offset.inputs["X"])
    links.new(offset_y.outputs[0], top_offset.inputs["Y"])
    top_offset.inputs["Z"].default_value = 0.0

    # Náklon ve směru posunu: +rotY sklápí vršek k +X, -rotX sklápí vršek k +Y.
    tilt_y = add_node(nodes, "ShaderNodeMath", -300, -1160, "Tilt Y")
    tilt_y.operation = "MULTIPLY"
    links.new(cos_a.outputs[0], tilt_y.inputs[0])
    links.new(sock(group_in, "outputs", "Top Tire Tilt"), tilt_y.inputs[1])

    tilt_x = add_node(nodes, "ShaderNodeMath", -300, -1340, "Tilt X")
    tilt_x.operation = "MULTIPLY"
    links.new(sin_a.outputs[0], tilt_x.inputs[0])
    links.new(sock(group_in, "outputs", "Top Tire Tilt"), tilt_x.inputs[1])

    tilt_x_neg = add_node(nodes, "ShaderNodeMath", -40, -1340, "Negate Tilt X")
    tilt_x_neg.operation = "MULTIPLY"
    links.new(tilt_x.outputs[0], tilt_x_neg.inputs[0])
    tilt_x_neg.inputs[1].default_value = -1.0

    top_euler = add_node(nodes, "ShaderNodeCombineXYZ", 220, -1160, "Top Tilt Euler")
    links.new(tilt_x_neg.outputs[0], top_euler.inputs["X"])
    links.new(tilt_y.outputs[0], top_euler.inputs["Y"])
    top_euler.inputs["Z"].default_value = 0.0

    switch_offset = add_node(nodes, "GeometryNodeSwitch", 260, -280, "Offset Switch")
    switch_offset.input_type = "VECTOR"
    connect(links, is_top, "Result", switch_offset, "Switch")
    connect(links, jitter, "Value", switch_offset, "False")
    connect(links, top_offset, "Vector", switch_offset, "True")

    switch_tilt = add_node(nodes, "GeometryNodeSwitch", 520, -1160, "Tilt Switch")
    switch_tilt.input_type = "VECTOR"
    connect(links, is_top, "Result", switch_tilt, "Switch")
    connect(links, top_euler, "Vector", switch_tilt, "True")

    tilt_rot = add_node(nodes, "FunctionNodeEulerToRotation", 820, -1160, "Tilt Rotation")
    connect(links, switch_tilt, "Output", tilt_rot, "Euler")

    instance = add_node(nodes, "GeometryNodeInstanceOnPoints", 680, 460, "Instance on Points")
    connect(links, stack_points, "Geometry", instance, "Points")
    connect(links, centered, "Geometry", instance, "Instance")

    translate = add_node(nodes, "GeometryNodeTranslateInstances", 980, 460, "Translate Instances")
    translate.inputs["Local Space"].default_value = False
    connect(links, instance, "Instances", translate, "Instances")
    connect(links, switch_offset, "Output", translate, "Translation")

    # Local Space: rotace kolem vlastního počátku instance, ne kolem počátku objektu.
    rotate_spin = add_node(nodes, "GeometryNodeRotateInstances", 1280, 400, "Rotate Tread")
    rotate_spin.inputs["Local Space"].default_value = True
    connect(links, translate, "Instances", rotate_spin, "Instances")
    connect(links, spin_rot, "Rotation", rotate_spin, "Rotation")

    # Pivot = Position, ať náklon v globálním XY krouží kolem pneumatiky, ne kolem nuly.
    pivot = add_node(nodes, "GeometryNodeInputPosition", 1420, 120, "Instance Position")
    rotate_tilt = add_node(nodes, "GeometryNodeRotateInstances", 1580, 360, "Rotate Top Tilt")
    rotate_tilt.inputs["Local Space"].default_value = False
    connect(links, rotate_spin, "Instances", rotate_tilt, "Instances")
    connect(links, tilt_rot, "Rotation", rotate_tilt, "Rotation")
    connect(links, pivot, "Position", rotate_tilt, "Pivot Point")

    realize = add_node(nodes, "GeometryNodeRealizeInstances", 1880, 360, "Realize Instances")
    connect(links, rotate_tilt, "Instances", realize, "Geometry")
    if "Realize All" in realize.inputs:
        realize.inputs["Realize All"].default_value = True

    show_real = add_node(nodes, "GeometryNodeSwitch", 2100, 360, "Realize Switch")
    show_real.input_type = "GEOMETRY"
    connect(links, group_in, "Realize Instances", show_real, "Switch")
    connect(links, rotate_tilt, "Instances", show_real, "False")
    connect(links, realize, "Geometry", show_real, "True")
    connect(links, show_real, "Output", group_out, "Geometry")

    if hasattr(ng, "is_modifier"):
        ng.is_modifier = True
    for trait in ("is_type_mesh", "is_type_curve"):
        if hasattr(ng, trait):
            setattr(ng, trait, True)
    for item in ng.interface.items_tree:
        if getattr(item, "in_out", None) != "INPUT":
            continue
        if hasattr(item, "hide_in_modifier"):
            item.hide_in_modifier = False
    try:
        if ng.asset_data is None:
            ng.asset_mark()
    except RuntimeError:
        pass
    if ng.asset_data is not None:
        ng.asset_data.catalog_id = CATALOG_ID
        if hasattr(ng.asset_data, "description"):
            ng.asset_data.description = (
                "Bariéra z pneumatik podél křivky. "
                "Přetáhni na křivku, stejně jako TREES."
            )
    return ng


def set_modifier_input(mod, item, value):
    inputs = getattr(getattr(mod, "properties", None), "inputs", None)
    if inputs is not None and hasattr(inputs, item.identifier):
        socket = getattr(inputs, item.identifier)
        if hasattr(socket, "value"):
            socket.value = value
            return
    mod[item.identifier] = value


def assign_modifier(obj, ng, tire):
    mod = next(
        (item for item in obj.modifiers if item.type == "NODES" and item.name == MODIFIER_NAME),
        None,
    )
    if mod is None:
        mod = obj.modifiers.new(MODIFIER_NAME, "NODES")
    mod.node_group = ng
    mod.show_viewport = True
    mod.show_render = True
    mod.show_expanded = True

    values = dict(DEFAULTS)
    values["Tire Object"] = tire
    for item in ng.interface.items_tree:
        if getattr(item, "in_out", None) != "INPUT":
            continue
        if item.name not in values:
            continue
        if item.name == "Tire Object" and hasattr(item, "default_value"):
            item.default_value = tire
        set_modifier_input(mod, item, values[item.name])
    return mod


def activate(obj):
    view_layer = bpy.context.view_layer
    for other in view_layer.objects:
        if other.hide_select:
            continue
        if other.select_get():
            other.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    obj.update_tag()
    view_layer.update()


def library_directory():
    if "__file__" in globals():
        return os.path.dirname(os.path.abspath(__file__))
    if bpy.data.filepath:
        return os.path.dirname(bpy.path.abspath(bpy.data.filepath))
    return os.getcwd()


def write_catalog(directory):
    path = os.path.join(directory, "blender_assets.cats.txt")
    contents = (
        "# This is an Asset Catalog Definition file for Blender.\n"
        "#\n"
        "# Empty lines and lines starting with `#` will be ignored.\n"
        "# The first non-ignored line should be the version indicator.\n"
        "# Other lines are of the format \"UUID:catalog/path/for/assets:simple catalog name\"\n"
        "\n"
        "VERSION 1\n"
        "\n"
        f"{CATALOG_ID}:{CATALOG_PATH}:{CATALOG_PATH}\n"
    )
    existing = ""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            existing = handle.read()
    if CATALOG_ID in existing:
        return path
    with open(path, "a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        if "VERSION 1" not in existing:
            handle.write(contents)
        else:
            handle.write(f"{CATALOG_ID}:{CATALOG_PATH}:{CATALOG_PATH}\n")
    return path


def save_asset_library(tire):
    tire.use_fake_user = True
    directory = library_directory()
    write_catalog(directory)
    try:
        bpy.ops.file.pack_all()
    except RuntimeError as exc:
        print(f"Textury se nepodařilo zabalit: {exc}")
    path = os.path.join(directory, ASSET_BLEND)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print(f"Asset library: {path}")
    return path


def main():
    save_asset = "--save-asset" in sys.argv
    if save_asset:
        for obj in list(bpy.context.selected_objects):
            obj.select_set(False)
        bpy.context.view_layer.objects.active = None

    enter_object_mode()
    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)

    tire = ensure_tire_object()
    target = pick_target(tire, previous_active, previous_selected)
    group = build_group()
    assign_modifier(target, group, tire)
    activate(target)
    if save_asset:
        save_asset_library(tire)
    print(
        f"TireBarrier: modifikátor na „{target.name}“, pneumatika „{tire.name}“. "
        "V Asset Browseru ho přetáhni na křivku."
    )
    return target


if __name__ == "__main__":
    main()
