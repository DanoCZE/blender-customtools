"""Vegetace jako Geometry Nodes modifikátor.

Jednou spusť skript na mesh terénu. Naimportuje grass.fbx: nízkou trávu,
vysokou trávu a kopřivy, včetně textur. Potom weight paintem maluj
vertex groups Trava, Vysoka, Koprivy, Plevel a Louka. Váha 0 nic nezasadí,
váha 1 sází plnou hustotou.

Louka je jeden weight a uvnitř míchá nízkou trávu, pampelišky, sedmikrásky
a jetel. Nízká tráva v louce bere stejnou kolekci jako vrstva Trava.
"""

from __future__ import annotations

import math
import os
import sys

import bpy
import mathutils
from bpy.app.handlers import persistent

GROUP_NAME = "Vegetation"
MODIFIER_NAME = "Vegetation"
FBX_NAME = "grass.fbx"
SOURCE_FLAG = "vegetation_source"
PARENT_COLLECTION = "Vegetation"
MTIME_KEY = "vegetation_fbx_mtime"
ROLE_KEY = "vegetation_role"
ASSET_BLEND = "Vegetation.blend"
CATALOG_ID = "c4e8a1b7-2f63-4d90-9a15-6e0b8c3d7f21"
CATALOG_PATH = "Modifiers"
PLANTED = ("Trava", "Vysoka", "Koprivy")
SUBCOLLECTIONS = PLANTED + ("Plevel", "Pampelisky", "Sedmikrasky", "Jetel")

VERTEX_GROUPS = ("Trava", "Vysoka", "Koprivy", "Plevel", "Louka")

DEFAULTS = {
    "Trava Density": 80.0,
    "Trava Scale Min": 0.8,
    "Trava Scale Max": 1.2,
    "Vysoka Density": 3.0,
    "Vysoka Scale Min": 0.8,
    "Vysoka Scale Max": 1.2,
    "Koprivy Density": 4.0,
    "Koprivy Scale Min": 0.8,
    "Koprivy Scale Max": 1.2,
    "Plevel Density": 8.0,
    "Plevel Scale Min": 0.8,
    "Plevel Scale Max": 1.2,
    "Louka Trava Density": 60.0,
    "Louka Pampelisky Density": 1.5,
    "Louka Sedmikrasky Density": 2.0,
    "Louka Jetel Density": 3.0,
    "Louka Scale Min": 0.8,
    "Louka Scale Max": 1.2,
    "Seed": 0,
    "Height Variation": 0.2,
    "Tilt": math.radians(8.0),
    "Min Slope": 0.0,
    "Realize Instances": False,
}

# Posun Seed uvnitř vrstvy, ať rozmístění, výška, spin, náklon a varianta
# nedostanou z jednoho ID stejné číslo.
_DISTRIBUTE = 0
_SCALE = 1
_HEIGHT = 2
_SPIN = 3
_TILT = 4
_INDEX = 5

LAYERS = (
    {
        "label": "Trava",
        "weight": "Trava",
        "collection": "Trava",
        "density": "Trava Density",
        "scale_min": "Trava Scale Min",
        "scale_max": "Trava Scale Max",
        "seed_offset": 11,
    },
    {
        "label": "Vysoka",
        "weight": "Vysoka",
        "collection": "Vysoka",
        "density": "Vysoka Density",
        "scale_min": "Vysoka Scale Min",
        "scale_max": "Vysoka Scale Max",
        "seed_offset": 19,
    },
    {
        "label": "Koprivy",
        "weight": "Koprivy",
        "collection": "Koprivy",
        "density": "Koprivy Density",
        "scale_min": "Koprivy Scale Min",
        "scale_max": "Koprivy Scale Max",
        "seed_offset": 29,
    },
    {
        "label": "Plevel",
        "weight": "Plevel",
        "collection": "Plevel",
        "density": "Plevel Density",
        "scale_min": "Plevel Scale Min",
        "scale_max": "Plevel Scale Max",
        "seed_offset": 47,
    },
    {
        "label": "Louka Trava",
        "weight": "Louka",
        "collection": "Trava",
        "density": "Louka Trava Density",
        "scale_min": "Louka Scale Min",
        "scale_max": "Louka Scale Max",
        "seed_offset": 67,
    },
    {
        "label": "Pampelisky",
        "weight": "Louka",
        "collection": "Pampelisky",
        "density": "Louka Pampelisky Density",
        "scale_min": "Louka Scale Min",
        "scale_max": "Louka Scale Max",
        "seed_offset": 83,
    },
    {
        "label": "Sedmikrasky",
        "weight": "Louka",
        "collection": "Sedmikrasky",
        "density": "Louka Sedmikrasky Density",
        "scale_min": "Louka Scale Min",
        "scale_max": "Louka Scale Max",
        "seed_offset": 101,
    },
    {
        "label": "Jetel",
        "weight": "Louka",
        "collection": "Jetel",
        "density": "Louka Jetel Density",
        "scale_min": "Louka Scale Min",
        "scale_max": "Louka Scale Max",
        "seed_offset": 127,
    },
)


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
        os.path.join("vegetation", FBX_NAME),
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
        "Soubor grass.fbx nebyl nalezen. Hledáno v:\n" + "\n".join(searched)
    )


def enter_object_mode():
    if bpy.context.mode == "OBJECT":
        return
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")


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
                ng.interface.move_to_parent(
                    socket,
                    parent,
                    len(parent.interface_items) if hasattr(parent, "interface_items") else 0,
                )
            return socket
        raise


def new_panel(ng, name, description):
    try:
        return ng.interface.new_panel(name, description=description, default_closed=False)
    except TypeError:
        return ng.interface.new_panel(name)


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


def add_float_input(ng, name, default, description, minimum=0.0, maximum=None, kind="plain", parent=None):
    if kind == "angle":
        candidates = ("NodeSocketFloatAngle", "NodeSocketFloat")
        subtype = "ANGLE"
    elif kind == "factor":
        candidates = ("NodeSocketFloatFactor", "NodeSocketFloat")
        subtype = "FACTOR"
    else:
        candidates = ("NodeSocketFloat",)
        subtype = None
    socket = None
    socket_type = None
    errors = []
    for candidate in candidates:
        try:
            socket = new_interface_socket(
                ng,
                name,
                choose_socket_type(ng, (candidate,)),
                "INPUT",
                description,
                parent=parent,
            )
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
    if maximum is not None and hasattr(socket, "max_value"):
        socket.max_value = maximum
    return socket


def add_int_input(ng, name, default, description, minimum=0, parent=None):
    socket = new_interface_socket(
        ng,
        name,
        choose_socket_type(ng, ("NodeSocketInt",)),
        "INPUT",
        description,
        parent=parent,
    )
    socket.default_value = default
    if minimum is not None and hasattr(socket, "min_value"):
        socket.min_value = minimum
    return socket


def add_bool_input(ng, name, default, description, parent=None):
    socket = new_interface_socket(
        ng,
        name,
        choose_socket_type(ng, ("NodeSocketBool",)),
        "INPUT",
        description,
        parent=parent,
    )
    socket.default_value = default
    return socket


def add_collection_input(ng, name, description, parent=None):
    socket = new_interface_socket(
        ng,
        name,
        choose_socket_type(ng, ("NodeSocketCollection",)),
        "INPUT",
        description,
        parent=parent,
    )
    expose_picker(socket)
    return socket


def add_node(nodes, bl_idname, x, y, label=None):
    node = nodes.new(bl_idname)
    node.location = (x, y)
    if label:
        node.label = label
        node.name = label
    return node


def sock(node, collection, name, occurrence=0):
    named = [item for item in getattr(node, collection) if item.name == name]
    enabled = [item for item in named if getattr(item, "enabled", True)]
    pool = enabled or named
    if occurrence < len(pool):
        return pool[occurrence]
    available = ", ".join(item.name for item in getattr(node, collection)) or "(žádné)"
    label = node.label or node.name
    raise KeyError(
        f"Uzel {node.bl_idname} „{label}“ nemá {collection}.{name} #{occurrence}. "
        f"Dostupné: {available}"
    )


def connect(links, src_node, src_name, dst_node, dst_name, src_i=0, dst_i=0):
    links.new(
        sock(src_node, "outputs", src_name, src_i),
        sock(dst_node, "inputs", dst_name, dst_i),
    )


def set_bool(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value
        return
    if hasattr(node, name.lower().replace(" ", "_")):
        setattr(node, name.lower().replace(" ", "_"), value)


def math_node(nodes, operation, x, y, label):
    node = add_node(nodes, "ShaderNodeMath", x, y, label)
    node.operation = operation
    return node


def int_add(nodes, links, src_node, src_name, amount, x, y, label):
    node = add_node(nodes, "FunctionNodeIntegerMath", x, y, label)
    node.operation = "ADD"
    connect(links, src_node, src_name, node, "Value")
    sock(node, "inputs", "Value", 1).default_value = amount
    return node


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
        ng.description = (
            "Vegetace podle weight paintu. Groups Trava, Koprivy, Plevel a Louka."
        )
    ng.use_fake_user = True
    if previous is not None:
        for obj in bpy.data.objects:
            for mod in obj.modifiers:
                if mod.type == "NODES" and mod.node_group == previous:
                    mod.node_group = ng
        bpy.data.node_groups.remove(previous)
    return ng


def build_interface(ng):
    ng.interface.clear()
    new_interface_socket(
        ng,
        "Geometry",
        "NodeSocketGeometry",
        "INPUT",
        "Mesh terénu. Váha je ve vertex groups Trava, Koprivy, Plevel a Louka.",
    )

    panels = {
        "Trava": new_panel(ng, "Trava", "Nízká tráva malovaná groupou Trava."),
        "Vysoka": new_panel(ng, "Vysoka", "Vysoká tráva malovaná groupou Vysoka."),
        "Koprivy": new_panel(ng, "Koprivy", "Kopřivy malované groupou Koprivy."),
        "Plevel": new_panel(ng, "Plevel", "Plevel malovaný groupou Plevel."),
        "Louka": new_panel(
            ng,
            "Louka",
            "Jeden weight Louka. Tráva, pampelišky, sedmikrásky a jetel mají vlastní hustotu.",
        ),
        "Společné": new_panel(ng, "Společné", "Náhoda, náklon a sklon, společné pro všechny vrstvy."),
    }

    collections = {
        "Trava": (
            "Trava",
            "Nízká tráva z grass.fbx. Víc variant se střídá. Stejnou kolekci bere i tráva v louce.",
            panels["Trava"],
        ),
        "Vysoka": (
            "Vysoka",
            "Vysoká tráva z grass.fbx. Víc variant se střídá.",
            panels["Vysoka"],
        ),
        "Koprivy": (
            "Koprivy",
            "Kopřivy z grass.fbx.",
            panels["Koprivy"],
        ),
        "Plevel": ("Plevel", "Meshe plevele. Víc objektů v kolekci se střídá.", panels["Plevel"]),
        "Pampelisky": (
            "Pampelisky",
            "Meshe pampelišek pro vrstvu Louka.",
            panels["Louka"],
        ),
        "Sedmikrasky": (
            "Sedmikrasky",
            "Meshe sedmikrásek pro vrstvu Louka.",
            panels["Louka"],
        ),
        "Jetel": ("Jetel", "Meshe jetelu pro vrstvu Louka.", panels["Louka"]),
    }
    for name, description, panel in collections.values():
        add_collection_input(ng, name, description, parent=panel)

    density_help = "Bodů na m² při váze 1. Mezi body je náhodná mezera, hustota je jen průměr."
    scale_min_help = "Nejmenší jednotné měřítko trsu."
    scale_max_help = "Největší jednotné měřítko trsu."

    def scales(panel, prefix):
        add_float_input(
            ng,
            f"{prefix} Scale Min",
            DEFAULTS[f"{prefix} Scale Min"],
            scale_min_help,
            parent=panel,
        )
        add_float_input(
            ng,
            f"{prefix} Scale Max",
            DEFAULTS[f"{prefix} Scale Max"],
            scale_max_help,
            parent=panel,
        )

    for label, panel_name, density_name in (
        ("Trava", "Trava", "Trava Density"),
        ("Vysoka", "Vysoka", "Vysoka Density"),
        ("Koprivy", "Koprivy", "Koprivy Density"),
        ("Plevel", "Plevel", "Plevel Density"),
    ):
        panel = panels[panel_name]
        add_float_input(
            ng,
            density_name,
            DEFAULTS[density_name],
            f"{density_help} Vertex group {label}.",
            parent=panel,
        )
        scales(panel, label)

    louka = panels["Louka"]
    for density_name, group_note in (
        ("Louka Trava Density", "Tráva v louce, mesh z kolekce Trava."),
        ("Louka Pampelisky Density", "Pampelišky v louce."),
        ("Louka Sedmikrasky Density", "Sedmikrásky v louce."),
        ("Louka Jetel Density", "Jetel v louce."),
    ):
        add_float_input(
            ng,
            density_name,
            DEFAULTS[density_name],
            f"{group_note} {density_help} Vertex group Louka.",
            parent=louka,
        )
    scales(louka, "Louka")

    shared = panels["Společné"]
    add_int_input(
        ng,
        "Seed",
        DEFAULTS["Seed"],
        "Posun náhody pro rozmístění, výšku, otočení i výběr varianty.",
        parent=shared,
    )
    add_float_input(
        ng,
        "Height Variation",
        DEFAULTS["Height Variation"],
        "Náhodný rozdíl výšky navíc k jednotnému měřítku. 0,2 je zhruba ±20 % na ose Z.",
        maximum=1.0,
        kind="factor",
        parent=shared,
    )
    add_float_input(
        ng,
        "Tilt",
        DEFAULTS["Tilt"],
        "Největší náhodný náklon do strany, v radiánech.",
        minimum=0.0,
        kind="angle",
        parent=shared,
    )
    add_float_input(
        ng,
        "Min Slope",
        DEFAULTS["Min Slope"],
        "Nejnižší složka Z normály, na kterou se ještě sází. 0 limit vypne.",
        maximum=1.0,
        kind="factor",
        parent=shared,
    )
    add_bool_input(
        ng,
        "Realize Instances",
        DEFAULTS["Realize Instances"],
        "Sloučí rostliny do jednoho meshe. Zapni až před Object → Convert → Mesh.",
        parent=shared,
    )
    new_interface_socket(ng, "Geometry", "NodeSocketGeometry", "OUTPUT")


def build_slope_mask(nodes, links, group_in):
    """Výběr faců. Min Slope 0 nechá malbu projít i na strmý svah."""
    normal = add_node(nodes, "GeometryNodeInputNormal", -2100, 1680, "Face Normal")
    split = add_node(nodes, "ShaderNodeSeparateXYZ", -1900, 1680, "Normal Z")
    connect(links, normal, "Normal", split, "Vector")

    steep = add_node(nodes, "FunctionNodeCompare", -1680, 1760, "Steep Enough")
    steep.data_type = "FLOAT"
    steep.operation = "GREATER_EQUAL"
    connect(links, split, "Z", steep, "A")
    connect(links, group_in, "Min Slope", steep, "B")

    disabled = add_node(nodes, "FunctionNodeCompare", -1680, 1560, "Slope Off")
    disabled.data_type = "FLOAT"
    disabled.operation = "LESS_EQUAL"
    connect(links, group_in, "Min Slope", disabled, "A")
    sock(disabled, "inputs", "B").default_value = 0.0

    either = add_node(nodes, "FunctionNodeBooleanMath", -1460, 1660, "Slope Mask")
    either.operation = "OR"
    connect(links, disabled, "Result", either, "Boolean")
    connect(links, steep, "Result", either, "Boolean", dst_i=1)
    return either


def build_height_range(nodes, links, group_in):
    low = math_node(nodes, "SUBTRACT", -2100, 1320, "Height Min")
    sock(low, "inputs", "Value").default_value = 1.0
    connect(links, group_in, "Height Variation", low, "Value", dst_i=1)
    high = math_node(nodes, "ADD", -2100, 1160, "Height Max")
    sock(high, "inputs", "Value").default_value = 1.0
    connect(links, group_in, "Height Variation", high, "Value", dst_i=1)
    return low, high


def build_tilt_min(nodes, links, group_in):
    negative = math_node(nodes, "MULTIPLY", -2100, 1000, "Tilt Negative")
    connect(links, group_in, "Tilt", negative, "Value")
    sock(negative, "inputs", "Value", 1).default_value = -1.0
    return negative


def axis_angle(nodes, links, axis, angle_node, angle_name, x, y, label):
    node = add_node(nodes, "FunctionNodeAxisAngleToRotation", x, y, label)
    node.inputs["Axis"].default_value = axis
    connect(links, angle_node, angle_name, node, "Angle")
    return node


def rotate_by(nodes, links, rotation_node, by_node, x, y, label):
    if hasattr(bpy.types, "FunctionNodeRotateRotation"):
        node = add_node(nodes, "FunctionNodeRotateRotation", x, y, label)
        if hasattr(node, "rotation_space"):
            node.rotation_space = "LOCAL"
        connect(links, rotation_node, "Rotation", node, "Rotation")
        connect(links, by_node, "Rotation", node, "Rotate By")
        return node

    node = add_node(nodes, "FunctionNodeRotateEuler", x, y, label)
    node.rotation_type = "AXIS_ANGLE"
    if hasattr(node, "space"):
        node.space = "LOCAL"
    connect(links, rotation_node, "Rotation", node, "Rotation")
    connect(links, by_node, "Axis", node, "Axis")
    connect(links, by_node, "Angle", node, "Angle")
    return node


def align_to_normal(nodes, links, normal_node, x, y, label):
    if hasattr(bpy.types, "FunctionNodeAlignRotationToVector"):
        node = add_node(nodes, "FunctionNodeAlignRotationToVector", x, y, label)
    else:
        node = add_node(nodes, "FunctionNodeAlignEulerToVector", x, y, label)
    if hasattr(node, "axis"):
        node.axis = "Z"
    connect(links, normal_node, "Normal", node, "Vector")
    return node


def random_float(nodes, links, id_node, seed_node, minimum, maximum, x, y, label, min_node=None, max_node=None):
    node = add_node(nodes, "FunctionNodeRandomValue", x, y, label)
    node.data_type = "FLOAT"
    if min_node is None:
        sock(node, "inputs", "Min").default_value = minimum
    else:
        connect(links, min_node, "Value", node, "Min")
    if max_node is None:
        sock(node, "inputs", "Max").default_value = maximum
    else:
        connect(links, max_node, "Value", node, "Max")
    connect(links, id_node, "ID", node, "ID")
    connect(links, seed_node, "Value", node, "Seed")
    return node


def build_rotation(nodes, links, points, id_node, group_in, tilt_min, seed_base, x, y, label):
    aligned = align_to_normal(nodes, links, points, x, y + 80, f"{label} Align")

    spin_seed = int_add(
        nodes, links, seed_base, "Value", _SPIN, x, y - 80, f"{label} Spin Seed"
    )
    spin_angle = random_float(
        nodes, links, id_node, spin_seed, 0.0, math.tau, x + 220, y - 80, f"{label} Spin Angle"
    )
    if hasattr(bpy.types, "FunctionNodeAxisAngleToRotation"):
        spin_by = axis_angle(
            nodes, links, (0.0, 0.0, 1.0), spin_angle, "Value", x + 440, y - 80, f"{label} Spin Axis"
        )
        spun = rotate_by(nodes, links, aligned, spin_by, x + 660, y + 40, f"{label} Spin")
    else:
        spun = add_node(nodes, "FunctionNodeRotateEuler", x + 440, y + 40, f"{label} Spin")
        spun.rotation_type = "AXIS_ANGLE"
        if hasattr(spun, "space"):
            spun.space = "LOCAL"
        spun.inputs["Axis"].default_value = (0.0, 0.0, 1.0)
        connect(links, aligned, "Rotation", spun, "Rotation")
        connect(links, spin_angle, "Value", spun, "Angle")

    tilt_seed = int_add(
        nodes, links, seed_base, "Value", _TILT, x, y - 240, f"{label} Tilt Seed"
    )
    tilt_angle = random_float(
        nodes,
        links,
        id_node,
        tilt_seed,
        0.0,
        0.0,
        x + 220,
        y - 240,
        f"{label} Tilt Angle",
        min_node=tilt_min,
        max_node=None,
    )
    connect(links, group_in, "Tilt", tilt_angle, "Max")
    if hasattr(bpy.types, "FunctionNodeAxisAngleToRotation"):
        tilt_by = axis_angle(
            nodes, links, (1.0, 0.0, 0.0), tilt_angle, "Value", x + 440, y - 240, f"{label} Tilt Axis"
        )
        tilted = rotate_by(nodes, links, spun, tilt_by, x + 660, y - 160, f"{label} Tilt")
    else:
        tilted = add_node(nodes, "FunctionNodeRotateEuler", x + 440, y - 160, f"{label} Tilt")
        tilted.rotation_type = "AXIS_ANGLE"
        if hasattr(tilted, "space"):
            tilted.space = "LOCAL"
        tilted.inputs["Axis"].default_value = (1.0, 0.0, 0.0)
        connect(links, spun, "Rotation", tilted, "Rotation")
        connect(links, tilt_angle, "Value", tilted, "Angle")
    return tilted


def build_scale(nodes, links, id_node, group_in, height_min, height_max, seed_base, layer, x, y):
    label = layer["label"]
    scale_seed = int_add(
        nodes, links, seed_base, "Value", _SCALE, x, y, f"{label} Scale Seed"
    )
    uniform = random_float(
        nodes,
        links,
        id_node,
        scale_seed,
        0.0,
        1.0,
        x + 220,
        y,
        f"{label} Uniform Scale",
    )
    connect(links, group_in, layer["scale_min"], uniform, "Min")
    connect(links, group_in, layer["scale_max"], uniform, "Max")

    height_seed = int_add(
        nodes, links, seed_base, "Value", _HEIGHT, x, y - 180, f"{label} Height Seed"
    )
    height = random_float(
        nodes,
        links,
        id_node,
        height_seed,
        1.0,
        1.0,
        x + 220,
        y - 180,
        f"{label} Height Factor",
        min_node=height_min,
        max_node=height_max,
    )
    tall = math_node(nodes, "MULTIPLY", x + 440, y - 80, f"{label} Height")
    connect(links, uniform, "Value", tall, "Value")
    connect(links, height, "Value", tall, "Value", dst_i=1)

    combine = add_node(nodes, "ShaderNodeCombineXYZ", x + 660, y - 40, f"{label} Scale")
    connect(links, uniform, "Value", combine, "X")
    connect(links, uniform, "Value", combine, "Y")
    connect(links, tall, "Value", combine, "Z")
    return combine


def scatter_layer(nodes, links, group_in, mask, id_node, height_min, height_max, tilt_min, layer, y):
    """Jedna hustota nad jednou vertex group. Louka tuhle funkci pustí čtyřikrát."""
    label = layer["label"]
    x = -2300

    weight = add_node(nodes, "GeometryNodeInputNamedAttribute", x, y + 40, f"{label} Weight")
    weight.data_type = "FLOAT"
    weight.inputs["Name"].default_value = layer["weight"]

    density = math_node(nodes, "MULTIPLY", x + 240, y + 40, f"{label} Density")
    connect(links, weight, "Attribute", density, "Value")
    connect(links, group_in, layer["density"], density, "Value", dst_i=1)

    seed_base = int_add(
        nodes, links, group_in, "Seed", layer["seed_offset"], x + 240, y - 140, f"{label} Seed"
    )
    dist_seed = int_add(
        nodes, links, seed_base, "Value", _DISTRIBUTE, x + 460, y - 140, f"{label} Dist Seed"
    )

    points = add_node(nodes, "GeometryNodeDistributePointsOnFaces", x + 480, y + 80, f"{label} Points")
    points.distribute_method = "RANDOM"
    connect(links, group_in, "Geometry", points, "Mesh")
    connect(links, mask, "Boolean", points, "Selection")
    connect(links, density, "Value", points, "Density")
    connect(links, dist_seed, "Value", points, "Seed")

    collection = add_node(nodes, "GeometryNodeCollectionInfo", x, y - 280, f"{label} Collection")
    if hasattr(collection, "transform_space"):
        collection.transform_space = "RELATIVE"
    set_bool(collection, "Separate Children", True)
    set_bool(collection, "Reset Children", True)
    connect(links, group_in, layer["collection"], collection, "Collection")

    size = add_node(nodes, "GeometryNodeAttributeDomainSize", x + 240, y - 300, f"{label} Count")
    size.component = "INSTANCES"
    connect(links, collection, "Instances", size, "Geometry")
    last = add_node(nodes, "FunctionNodeIntegerMath", x + 460, y - 300, f"{label} Last Index")
    last.operation = "SUBTRACT"
    connect(links, size, "Instance Count", last, "Value")
    sock(last, "inputs", "Value", 1).default_value = 1

    index_seed = int_add(
        nodes, links, seed_base, "Value", _INDEX, x + 680, y - 300, f"{label} Index Seed"
    )
    index = add_node(nodes, "FunctionNodeRandomValue", x + 900, y - 300, f"{label} Index")
    index.data_type = "INT"
    sock(index, "inputs", "Min").default_value = 0
    connect(links, last, "Value", index, "Max")
    connect(links, id_node, "ID", index, "ID")
    connect(links, index_seed, "Value", index, "Seed")

    rotation = build_rotation(
        nodes, links, points, id_node, group_in, tilt_min, seed_base, x + 760, y + 220, label
    )
    scale = build_scale(
        nodes, links, id_node, group_in, height_min, height_max, seed_base, layer, x + 760, y - 80
    )

    instance = add_node(nodes, "GeometryNodeInstanceOnPoints", x + 1680, y, f"{label} Instances")
    set_bool(instance, "Pick Instance", True)
    connect(links, points, "Points", instance, "Points")
    connect(links, collection, "Instances", instance, "Instance")
    connect(links, index, "Value", instance, "Instance Index")
    connect(links, rotation, "Rotation", instance, "Rotation")
    connect(links, scale, "Vector", instance, "Scale")
    return instance


def finish_group(ng):
    if hasattr(ng, "is_modifier"):
        ng.is_modifier = True
    for trait, enabled in (
        ("is_type_mesh", True),
        ("is_type_curve", False),
        ("is_type_pointcloud", False),
        ("is_type_grease_pencil", False),
    ):
        if hasattr(ng, trait):
            setattr(ng, trait, enabled)
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
                "Vegetace podle weight paintu. "
                "Groups Trava, Vysoka, Koprivy, Plevel a Louka."
            )
    return ng


def build_group():
    ng = rebuild_group()
    build_interface(ng)
    nodes = ng.nodes
    links = ng.links

    group_in = add_node(nodes, "NodeGroupInput", -2680, 200, "Group Input")
    group_in.width = 280
    group_out = add_node(nodes, "NodeGroupOutput", 2200, 200, "Group Output")
    group_out.is_active_output = True

    mask = build_slope_mask(nodes, links, group_in)
    height_min, height_max = build_height_range(nodes, links, group_in)
    tilt_min = build_tilt_min(nodes, links, group_in)
    id_node = add_node(nodes, "GeometryNodeInputID", -2100, 820, "Point ID")

    instances = []
    for index, layer in enumerate(LAYERS):
        instances.append(
            scatter_layer(
                nodes,
                links,
                group_in,
                mask,
                id_node,
                height_min,
                height_max,
                tilt_min,
                layer,
                2100 - index * 920,
            )
        )

    joined = add_node(nodes, "GeometryNodeJoinGeometry", 1680, 200, "Terrain And Plants")
    links.new(sock(group_in, "outputs", "Geometry"), sock(joined, "inputs", "Geometry"))
    for instance in instances:
        links.new(sock(instance, "outputs", "Instances"), sock(joined, "inputs", "Geometry"))

    realize = add_node(nodes, "GeometryNodeRealizeInstances", 1900, 40, "Realize Instances")
    if "Realize All" in realize.inputs:
        realize.inputs["Realize All"].default_value = True
    connect(links, joined, "Geometry", realize, "Geometry")

    show_real = add_node(nodes, "GeometryNodeSwitch", 1900, 280, "Realize Switch")
    show_real.input_type = "GEOMETRY"
    connect(links, group_in, "Realize Instances", show_real, "Switch")
    connect(links, joined, "Geometry", show_real, "False")
    connect(links, realize, "Geometry", show_real, "True")
    connect(links, show_real, "Output", group_out, "Geometry")
    return finish_group(ng)


def plant_role(name):
    key = name.lower()
    if "brennesel" in key or "nettle" in key or "kopriv" in key:
        return "Koprivy"
    if "tall" in key:
        return "Vysoka"
    if "grass" in key:
        return "Trava"
    return None


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
    return imported


def _scene_contains(root, collection):
    if root == collection:
        return True
    for child in root.children:
        if _scene_contains(child, collection):
            return True
    return False


def _unlink_collection(collection):
    scene_root = bpy.context.scene.collection
    if collection.name in scene_root.children:
        scene_root.children.unlink(collection)
    for parent in bpy.data.collections:
        if collection.name in parent.children:
            parent.children.unlink(collection)


def parent_collection():
    collection = bpy.data.collections.get(PARENT_COLLECTION)
    if collection is None:
        legacy = bpy.data.collections.get("Vegetation_Source")
        if legacy is not None:
            legacy.name = PARENT_COLLECTION
            collection = legacy
        else:
            collection = bpy.data.collections.new(PARENT_COLLECTION)
    if not _scene_contains(bpy.context.scene.collection, collection):
        bpy.context.scene.collection.children.link(collection)
    return collection


def role_collection(name):
    parent = parent_collection()
    for child in parent.children:
        if child.name == name or child.name == f"Vegetation_{name}":
            if child.name != name and bpy.data.collections.get(name) is None:
                child.name = name
            return child
    legacy = bpy.data.collections.get(f"Vegetation_{name}")
    if legacy is not None:
        _unlink_collection(legacy)
        parent.children.link(legacy)
        if bpy.data.collections.get(name) is None:
            legacy.name = name
        return legacy
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    return collection


def move_to_collection(obj, collection):
    for owner in list(obj.users_collection):
        if owner != collection:
            owner.objects.unlink(obj)
    if obj.name not in collection.objects:
        collection.objects.link(obj)


def stash_source(obj):
    """Schová zdroj ve viewportu. hide_viewport by Collection Info vyprázdnilo."""
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


def bake_mesh(obj):
    """Velikost a otočení z FBX se zapíšou do vrcholů, spodek sedí na zemi.

    Kopřivy přijedou se scale 0,0001. Reset Children v uzlu by je bez toho
    natáhl na kilometry, protože objektové měřítko zahodí.
    """
    matrix = obj.matrix_basis.copy()
    matrix.translation = mathutils.Vector((0.0, 0.0, 0.0))
    if any(abs(value) > 1e-8 for row in matrix for value in row[:4]) and matrix != mathutils.Matrix.Identity(4):
        obj.data.transform(matrix)
    obj.matrix_basis = mathutils.Matrix.Identity(4)
    verts = obj.data.vertices
    if not verts:
        return
    xs = [vert.co.x for vert in verts]
    ys = [vert.co.y for vert in verts]
    zmin = min(vert.co.z for vert in verts)
    center_x = (min(xs) + max(xs)) * 0.5
    center_y = (min(ys) + max(ys)) * 0.5
    for vert in verts:
        vert.co.x -= center_x
        vert.co.y -= center_y
        vert.co.z -= zmin
    obj.data.update()


def _norm_name(name):
    return "".join(char for char in name.lower() if char.isalnum())


def _find_named(folder, target, max_depth=3):
    if not folder or not os.path.isdir(folder):
        return None
    root = os.path.abspath(folder)
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) - base_depth
        if depth >= max_depth:
            dirnames.clear()
            continue
        for filename in filenames:
            if _norm_name(filename) == target:
                return os.path.join(dirpath, filename)
    return None


def resolve_texture(image):
    target = _norm_name(os.path.basename(image.filepath or image.name))
    local = _find_named(os.path.join(library_directory(), "textures"), target, max_depth=2) if target else None
    if local:
        return local
    raw = bpy.path.abspath(image.filepath) if image.filepath else ""
    if raw and os.path.isfile(raw):
        return raw
    if not target:
        return None
    folders = []
    if raw:
        folder = os.path.dirname(raw)
        folders.extend((folder, os.path.dirname(folder)))
    folders.append(library_directory())
    seen = set()
    for folder in folders:
        if not folder or folder in seen:
            continue
        seen.add(folder)
        found = _find_named(folder, target)
        if found:
            return found
    return None


def adopt_textures(objects):
    seen = set()
    for obj in objects:
        if obj.type != "MESH":
            continue
        for mat in obj.data.materials:
            if mat is None or mat.node_tree is None:
                continue
            mat[SOURCE_FLAG] = True
            if hasattr(mat, "use_backface_culling"):
                mat.use_backface_culling = False
            for node in list(mat.node_tree.nodes):
                if node.type != "TEX_IMAGE" or node.image is None:
                    continue
                image = node.image
                key = image.as_pointer()
                if key in seen:
                    continue
                seen.add(key)
                path = resolve_texture(image)
                if path is None:
                    print(f"Vegetation: chybí textura „{image.name}“ ({image.filepath}).")
                    for output in node.outputs:
                        for link in list(output.links):
                            mat.node_tree.links.remove(link)
                    continue
                if os.path.abspath(bpy.path.abspath(image.filepath or "")) != os.path.abspath(path):
                    image.filepath = path
                    image.reload()
                color = node.outputs.get("Color")
                if color is not None and any(link.to_node.type == "NORMAL_MAP" for link in color.links):
                    try:
                        image.colorspace_settings.name = "Non-Color"
                    except TypeError:
                        pass
                image[SOURCE_FLAG] = True
                if image.packed_file is None:
                    try:
                        image.pack()
                    except RuntimeError as exc:
                        print(f"Vegetation: texturu „{image.name}“ se nepodařilo zabalit: {exc}")


def is_known_plant(obj):
    if getattr(obj, "type", None) != "MESH":
        return False
    role = obj.get(ROLE_KEY) or plant_role(obj.name)
    if role not in PLANTED:
        return False
    if obj.get(SOURCE_FLAG):
        return True
    key = obj.name.lower()
    return key.startswith("grass main") or key.startswith("grass tall") or key.startswith("brennesel")


def plant_collections():
    return {name: role_collection(name) for name in SUBCOLLECTIONS}


def adopt_existing_plants(collections):
    """Přesune už načtené rostliny do Vegetation / druh. Znovu je nezakládá."""
    for obj in list(bpy.data.objects):
        if not is_known_plant(obj):
            continue
        role = obj.get(ROLE_KEY) or plant_role(obj.name)
        if role not in collections:
            continue
        obj[SOURCE_FLAG] = True
        obj[ROLE_KEY] = role
        if obj.name not in collections[role].objects:
            move_to_collection(obj, collections[role])


def discard_object(obj):
    mesh = obj.data if obj.type == "MESH" else None
    mats = list(mesh.materials) if mesh is not None else []
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    for mat in mats:
        if mat is None or mat.users > 0:
            continue
        images = []
        if mat.node_tree is not None:
            images = [
                node.image
                for node in mat.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image is not None
            ]
        bpy.data.materials.remove(mat)
        for image in images:
            if image.users == 0:
                bpy.data.images.remove(image)


def source_mtime():
    times = [
        float(obj.get(MTIME_KEY, 0.0))
        for obj in bpy.data.objects
        if obj.get(SOURCE_FLAG) and obj.get(ROLE_KEY) in PLANTED
    ]
    if not times:
        return None
    return max(times)


def drop_source_plants():
    for obj in list(bpy.data.objects):
        if not obj.get(SOURCE_FLAG):
            continue
        role = obj.get(ROLE_KEY) or plant_role(obj.name)
        if role in PLANTED:
            discard_object(obj)


def ensure_plant_sources():
    collections = plant_collections()
    adopt_existing_plants(collections)
    path = resolve_fbx_path()
    mtime = os.path.getmtime(path)
    stored = source_mtime()
    stale = stored is None or mtime > stored + 1.0
    has_plants = all(
        any(obj.type == "MESH" for obj in collections[name].objects) for name in PLANTED
    )
    if has_plants and not stale:
        counts = ", ".join(f"{name} {len(collections[name].objects)}" for name in PLANTED)
        print(f"Vegetation: rostliny už v kolekci {PARENT_COLLECTION} jsou ({counts}).")
        return collections
    if has_plants:
        drop_source_plants()
        print("Vegetation: grass.fbx je novější, rostliny se nahradí.")

    missing = [
        name
        for name in PLANTED
        if not any(obj.type == "MESH" for obj in collections[name].objects)
    ]
    if not missing:
        return collections
    imported = import_fbx_objects(path)
    fresh = []
    for obj in imported:
        if obj.type != "MESH":
            discard_object(obj)
            continue
        role = plant_role(obj.name)
        if role is None:
            print(f"Vegetation: mesh „{obj.name}“ v grass.fbx nemá známou roli, přeskakuji.")
            discard_object(obj)
            continue
        if role not in missing:
            discard_object(obj)
            continue
        obj[SOURCE_FLAG] = True
        obj[MTIME_KEY] = mtime
        obj[ROLE_KEY] = role
        bake_mesh(obj)
        move_to_collection(obj, collections[role])
        stash_source(obj)
        fresh.append(obj)
    adopt_textures(fresh)
    counts = ", ".join(f"{name} {len(collections[name].objects)}" for name in PLANTED)
    print(f"Vegetation: grass.fbx → {counts}.")
    return collections


def set_modifier_input(mod, item, value):
    inputs = getattr(getattr(mod, "properties", None), "inputs", None)
    if inputs is not None and hasattr(inputs, item.identifier):
        socket = getattr(inputs, item.identifier)
        if hasattr(socket, "value"):
            socket.value = value
            return
    mod[item.identifier] = value


def assign_modifier(obj, ng):
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

    for item in ng.interface.items_tree:
        if getattr(item, "in_out", None) != "INPUT":
            continue
        if item.name not in DEFAULTS:
            continue
        set_modifier_input(mod, item, DEFAULTS[item.name])
    return mod


def bind_collections(ng, mod, sources):
    for item in ng.interface.items_tree:
        if getattr(item, "in_out", None) != "INPUT":
            continue
        collection = sources.get(item.name)
        if collection is None:
            continue
        if hasattr(item, "default_value"):
            try:
                item.default_value = collection
            except (TypeError, ValueError):
                pass
        if mod is not None:
            set_modifier_input(mod, item, collection)


def ensure_vertex_groups(obj, select_trava=False):
    created = []
    previous = obj.vertex_groups.active
    for name in VERTEX_GROUPS:
        if obj.vertex_groups.get(name) is None:
            obj.vertex_groups.new(name=name)
            created.append(name)
    if not created:
        return created
    if select_trava or previous is None or len(created) == len(VERTEX_GROUPS):
        trava = obj.vertex_groups.get("Trava")
        if trava is not None:
            obj.vertex_groups.active = trava
    else:
        obj.vertex_groups.active = previous
    return created


def uses_vegetation(obj):
    if obj.get(SOURCE_FLAG):
        return False
    for mod in obj.modifiers:
        group = getattr(mod, "node_group", None)
        if mod.type == "NODES" and group is not None and group.name == GROUP_NAME:
            return True
    return False


_PENDING_GROUPS = []
_GROUPS_TIMER = False


def flush_pending_groups():
    """Vertex groups nelze založit přímo v depsgraph handleru, Blender je zahodí."""
    global _GROUPS_TIMER
    _GROUPS_TIMER = False
    pending = list(_PENDING_GROUPS)
    _PENDING_GROUPS.clear()
    for obj in pending:
        try:
            alive = obj.type == "MESH"
        except ReferenceError:
            continue
        if alive and uses_vegetation(obj):
            ensure_vertex_groups(obj)
    return None


@persistent
def sync_vertex_groups(scene, depsgraph):
    """Doplní groupy na mesh, jakmile na něm je modifikátor Vegetation."""
    global _GROUPS_TIMER
    for update in depsgraph.updates:
        ident = getattr(update, "id", None)
        if not isinstance(ident, bpy.types.Object) or ident.type != "MESH":
            continue
        if getattr(ident, "is_evaluated", False):
            ident = ident.original
        if not uses_vegetation(ident) or ident in _PENDING_GROUPS:
            continue
        _PENDING_GROUPS.append(ident)
    if _PENDING_GROUPS and not _GROUPS_TIMER:
        _GROUPS_TIMER = True
        bpy.app.timers.register(flush_pending_groups, first_interval=0.0)


@persistent
def sync_existing_groups(_dummy):
    def run():
        for obj in bpy.data.objects:
            if getattr(obj, "type", None) == "MESH" and uses_vegetation(obj):
                ensure_vertex_groups(obj)
        return None

    bpy.app.timers.register(run, first_interval=0.1)


def register_group_handler():
    updates = bpy.app.handlers.depsgraph_update_post
    if sync_vertex_groups not in updates:
        updates.append(sync_vertex_groups)
    loads = bpy.app.handlers.load_post
    if sync_existing_groups not in loads:
        loads.append(sync_existing_groups)


def pick_target(previous_active, previous_selected):
    if (
        previous_active is not None
        and previous_active.type == "MESH"
        and previous_active in previous_selected
    ):
        return previous_active
    for obj in previous_selected:
        if obj.type == "MESH":
            return obj
    raise RuntimeError("Vyber mesh, na který se má vegetace nakreslit.")


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


def save_asset_library():
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
    enter_object_mode()
    previous_active = bpy.context.view_layer.objects.active
    previous_selected = list(bpy.context.selected_objects)

    target = None
    try:
        target = pick_target(previous_active, previous_selected)
    except RuntimeError:
        if not save_asset:
            raise

    sources = ensure_plant_sources()
    group = build_group()
    mod = None
    if target is not None:
        ensure_vertex_groups(target, select_trava=True)
        register_group_handler()
        mod = assign_modifier(target, group)
        activate(target)
        print(
            f"Vegetation: modifikátor na „{target.name}“. "
            "Maluj groups Trava, Vysoka, Koprivy, Plevel a Louka."
        )
    bind_collections(group, mod, sources)
    if save_asset:
        save_asset_library()
    elif target is None:
        raise RuntimeError("Vyber mesh, na který se má vegetace nakreslit.")
    return target


if __name__ == "__main__":
    main()
