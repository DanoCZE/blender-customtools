# blender-customtools

Vlastní nástroje pro Blender na stavbu tratí. Každý nástroj je Geometry Nodes modifikátor: jednou se spustí skript, potom se používá stejně jako TREES v TrackTools.

## Knihovna

`customtools.blend` v kořeni drží všechny skupiny, teď **Tire Barrier** a **Vegetation**, včetně pneumatiky, rostlin a zabalených textur. Katalog je `blender_assets.cats.txt`.

Přegenerování:

```text
blender --python build_library.py
```

Ve **Edit → Preferences → File Paths → Asset Libraries** přidej kořenovou složku projektu. Modifikátor pak přetáhni z Asset Browseru.

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

Skupina je v `customtools.blend`, viz Knihovna.

## Vegetation

`vegetation/vegetation.py` rozsází rostliny na mesh podle weight paintu. Váha 0 nic nezasadí, váha 1 sází plnou hustotou. Rozmístění není mřížka: hustota je jen průměrná mezera.

Skript naimportuje `vegetation/grass.fbx`. Nízká tráva (`Grass main`) jde do **Trava**, vysoká (`Grass tall`) do **Vysoka**, kopřivy (`Brennesel`) do **Koprivy**. Textury bere přednostně ze `vegetation/textures` a zabalí je do scény. Novější `grass.fbx` rostliny nahradí. Plevel, pampelišky, sedmikrásky a jetel zatím vlastní mesh nemají.

### Požadavky

- Blender 4.0 nebo novější s Geometry Nodes
- `vegetation/grass.fbx` a textury, na které odkazuje (nízká tráva, vysoká tráva, kopřivy)

### Spuštění

1. Otevři scénu v Blenderu.
2. Vyber mesh terénu.
3. Spusť skript ze Scripting workspace, nebo z příkazové řádky:

```text
blender soubor.blend --python vegetation/vegetation.py
```

Skript založí vertex groups **Trava**, **Vysoka**, **Koprivy**, **Plevel** a **Louka**, naimportuje rostliny z `grass.fbx` a na mesh přidá modifikátor **Vegetation**. Aktivní groupa je Trava, takže weight paint začne nízkou trávou.

Další povrchy už skript nepotřebují. Modifikátor přidej přes **Add Modifier → Vegetation**, nebo ho z Asset Browseru přetáhni na mesh. Groupy **Trava**, **Vysoka**, **Koprivy**, **Plevel** a **Louka** se na meshi založí samy. Po aktualizaci skriptu stačí Blender jednou restartovat.

### Vrstvy

| Group | Co se sází |
| --- | --- |
| Trava | nízká tráva z `grass.fbx` |
| Vysoka | vysoká tráva z `grass.fbx` |
| Koprivy | kopřivy z `grass.fbx` |
| Plevel | plevel, kolekce se přiřazuje ručně |
| Louka | nízká tráva, pampelišky, sedmikrásky a jetel, každý vlastní hustotou |

Kolekce **Trava** je společná pro group Trava i pro trávu v louce. Pampelišky, sedmikrásky a jetel mají vlastní kolekci v panelu Louka.

### Parametry

| Parametr | Výchozí | Význam |
| --- | --- | --- |
| Density | 80 / 3 / 4 / 8 | Nízká tráva, vysoká tráva, kopřivy a plevel, body na m² při váze 1. |
| Louka Density | 60 / 1,5 / 2 / 3 | Tráva, pampelišky, sedmikrásky a jetel nad groupou Louka. |
| Scale Min / Max | 0,8–1,2 | Náhodné jednotné měřítko. Louka má jeden rozsah pro všechny čtyři druhy. |
| Seed | 0 | Posun náhody pro místo, mezeru, výšku, otočení i variantu. |
| Height Variation | 0,2 | Náhodná výška navíc, zhruba ±20 % na ose Z. |
| Tilt | 8° | Největší náhodný náklon do strany. Spin kolem normály je vždy 0–360°. |
| Min Slope | 0 | Nejnižší složka Z normály. 0 limit vypne, malba platí i na strmém svahu. |
| Realize Instances | vypnuto | Sloučí rostliny do jednoho meshe. |

### Uložení do scény

Zapni **Realize Instances** a použij **Object → Convert → Mesh**.

Skupina je v `customtools.blend`, viz Knihovna.
