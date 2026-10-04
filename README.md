# blender-customtools

Vlastní nástroje pro Blender na stavbu tratí. Každý nástroj je Geometry Nodes modifikátor: jednou se spustí skript, potom se používá stejně jako TREES v TrackTools.

## Tire Barrier

`tyre/tire_barrier.py` rozloží stohy pneumatik podél křivky. Rozestup stohů řídí **Distance**, stranu od křivky **Offset**. Když je vybraný terén, stohy se na něj připnou paprskem shora.

### Požadavky

- Blender 4.0 nebo novější s Geometry Nodes
- mesh pneumatiky v souboru `tyre.fbx` ve složce `tyre/` (skript ho hledá i o úroveň výš a v blízkých podsložkách)

### Spuštění

1. Otevři scénu v Blenderu.
2. Vyber křivku nebo mesh, na který se má bariéra přidat. Bez výběru skript vytvoří vlastní křivku **Tire Barrier** v místě 3D kurzoru.
3. Spusť skript ze Scripting workspace, nebo z příkazové řádky:

```text
blender soubor.blend --python tyre/tire_barrier.py
```

Skript naimportuje `tyre.fbx`, zdroj schová do kolekce `TireBarrier_Source` a na cíl přidá modifikátor **Tire Barrier**. Skupinu zároveň označí jako asset v katalogu **Modifiers**.

Další bariéry už skript nepotřebují. Modifikátor přidej přes **Add Modifier → Tire Barrier**, nebo ho z Asset Browseru (**Current File**) přetáhni na křivku.

### Parametry

| Parametr | Výchozí | Význam |
| --- | --- | --- |
| Curve | — | Křivka, podél které se bariéra rozloží. Bez ní se použije geometrie objektu s modifikátorem. |
| Terrain | — | Mesh terénu, na který se stohy připnou. |
| Tire Object | importovaný mesh | Pneumatika, která se instancuje. |
| Distance | 0,7 m | Rozestup stohů podél křivky. |
| Offset | 0 | Posun do strany. Záporná hodnota dá bariéru na druhou stranu. |
| Snap Distance | 100 m | Výška, odkud paprsek na terén začíná. Délka paprsku je dvojnásobek, směrem dolů. |
| Count | 5 | Počet pneumatik v jednom stohu. |
| Tire Height | 0,15 m | Svislý rozestup vrstev. |
| Jitter Amount | 0,05 m | Náhodný posun běžných pneumatik v rovině XY. |
| Top Tire Offset | 0,08 m | Posun vrchní pneumatiky v náhodném směru XY. |
| Top Tire Tilt | 11,5° | Náklon vrchní pneumatiky ve směru jejího posunu. |
| Seed | 0 | Posun náhody pro jitter, otočení a vrchní pneumatiku. |
| Realize Instances | zapnuto | Sloučí bariéru do jednoho meshe. |

### Uložení do scény

Nech **Realize Instances** zapnuté a použij **Object → Convert → Mesh**. Uloží se geometrie, kterou vidíš ve viewportu.

### Asset library

Složku `tyre` můžeš uložit jako knihovnu assetů:

```text
blender --python tyre/tire_barrier.py -- --save-asset
```

Vznikne `tyre/TireBarrier.blend`. Katalog je v `tyre/blender_assets.cats.txt`. Ve **Edit → Preferences → File Paths → Asset Libraries** přidej složku `tyre` a modifikátor pak přetahuj z Asset Browseru na křivku.
