"""Jeden blend v kořeni se všemi Geometry Nodes modifikátory.

Spusť z kořene projektu:

    blender --python build_library.py

Vznikne customtools.blend a blender_assets.cats.txt. Ve
Edit → Preferences → File Paths → Asset Libraries přidej tuhle složku.
"""

from __future__ import annotations

import importlib.util
import os

import bpy

ROOT = os.path.dirname(os.path.abspath(__file__))
BLEND_NAME = "customtools.blend"
CATALOG_ID = "7c1e4a92-6d08-4f3b-a1e5-9b2d84c0f6aa"
CATALOG_PATH = "Modifiers"


def load_module(name, relative):
    path = os.path.join(ROOT, relative)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clear_factory_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in (bpy.data.meshes, bpy.data.cameras, bpy.data.lights, bpy.data.curves):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def mark_asset(ng):
    ng.use_fake_user = True
    if ng.asset_data is None:
        ng.asset_mark()
    ng.asset_data.catalog_id = CATALOG_ID


def set_tire_default(ng, tire):
    for item in ng.interface.items_tree:
        if getattr(item, "in_out", None) != "INPUT" or item.name != "Tire Object":
            continue
        if hasattr(item, "default_value"):
            item.default_value = tire


def write_catalog():
    path = os.path.join(ROOT, "blender_assets.cats.txt")
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
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(contents)
    return path


def main():
    tire_mod = load_module("tire_barrier", os.path.join("tyre", "tire_barrier.py"))
    veg_mod = load_module("vegetation_tool", os.path.join("vegetation", "vegetation.py"))

    tire_mod.enter_object_mode()
    clear_factory_scene()

    tire = tire_mod.ensure_tire_object()
    tire.use_fake_user = True
    tire_group = tire_mod.build_group()
    set_tire_default(tire_group, tire)
    mark_asset(tire_group)

    sources = veg_mod.ensure_plant_sources()
    veg_group = veg_mod.build_group()
    veg_mod.bind_collections(veg_group, None, sources)
    mark_asset(veg_group)

    write_catalog()
    scene_root = bpy.context.scene.collection
    for collection in list(bpy.data.collections):
        if collection.objects or collection.children:
            continue
        if collection.name in scene_root.children:
            scene_root.children.unlink(collection)
        bpy.data.collections.remove(collection)
    try:
        bpy.ops.file.pack_all()
    except RuntimeError as exc:
        print(f"Textury se nepodařilo zabalit: {exc}")

    path = os.path.join(ROOT, BLEND_NAME)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    print(f"Knihovna: {path}")
    print(f"Skupiny: {tire_group.name}, {veg_group.name}")
    return path


if __name__ == "__main__":
    main()
