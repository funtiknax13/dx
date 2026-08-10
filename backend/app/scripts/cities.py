"""Build and load the canonical city list (GeoNames) used for the city picker.

Two steps, kept separate so production never needs to hit GeoNames at deploy:

  build  — download GeoNames dumps, process, and write a compact, committed
           `app/data/cities.csv.gz` (run locally when refreshing the data).
  load   — upsert that CSV into the `cities` table (run on deploy; idempotent).

Coverage: ALL populated places in Russia (RU.txt, feature class P — so small
towns/villages in Chuvashia and neighbouring republics are included), plus the
world's major cities (cities15000) outside Russia. Display names prefer the
Russian (Cyrillic) form; `name_ascii` keeps the Latin form so search matches
both "Москва" and "Moscow".

Data © GeoNames (https://www.geonames.org/), CC BY 4.0.
"""

import argparse
import asyncio
import csv
import gzip
import io
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path

_GEONAMES = "https://download.geonames.org/export/dump/"
_DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "cities.csv.gz"
_COLUMNS = [
    "id", "name", "name_ascii", "country_code", "country", "region", "lat", "lng", "population",
]

# ISO2 -> Russian country name for the places people actually pick; anything
# else falls back to the English name from countryInfo.txt.
_COUNTRY_RU = {
    "RU": "Россия", "BY": "Беларусь", "KZ": "Казахстан", "UA": "Украина",
    "UZ": "Узбекистан", "KG": "Киргизия", "TJ": "Таджикистан", "TM": "Туркмения",
    "AM": "Армения", "AZ": "Азербайджан", "GE": "Грузия", "MD": "Молдавия",
    "EE": "Эстония", "LV": "Латвия", "LT": "Литва", "DE": "Германия",
    "US": "США", "GB": "Великобритания", "FR": "Франция", "IT": "Италия",
    "ES": "Испания", "TR": "Турция", "CN": "Китай", "TH": "Таиланд",
    "AE": "ОАЭ", "CY": "Кипр", "GR": "Греция", "CZ": "Чехия", "PL": "Польша",
    "FI": "Финляндия", "RS": "Сербия", "ME": "Черногория", "PT": "Португалия",
    "NL": "Нидерланды", "AT": "Австрия", "CH": "Швейцария", "IL": "Израиль",
    "EG": "Египет", "IN": "Индия", "JP": "Япония", "KR": "Южная Корея",
    "VN": "Вьетнам", "ID": "Индонезия", "CA": "Канада",
}

# GeoNames' English admin1 name (from admin1CodesASCII.txt) -> Russian region.
# Keys are the exact strings GeoNames uses (verified against the build report);
# an unmapped region is stored NULL rather than shown in a mixed script.
_RU_REGION_RU = {
    "Adygeya Republic": "Адыгея",
    "Altai": "Республика Алтай",
    "Altai Krai": "Алтайский край",
    "Amur Oblast": "Амурская обл.",
    "Arkhangelskaya": "Архангельская обл.",
    "Astrakhan Oblast": "Астраханская обл.",
    "Bashkortostan Republic": "Башкортостан",
    "Belgorod Oblast": "Белгородская обл.",
    "Bryansk Oblast": "Брянская обл.",
    "Buryatiya Republic": "Бурятия",
    "Chechnya": "Чечня",
    "Chelyabinsk": "Челябинская обл.",
    "Chukotka": "Чукотский АО",
    "Chuvash Republic": "Чувашия",
    "Dagestan": "Дагестан",
    "Ingushetiya Republic": "Ингушетия",
    "Irkutsk Oblast": "Иркутская обл.",
    "Ivanovo Oblast": "Ивановская обл.",
    "Jewish Autonomous Oblast": "Еврейская АО",
    "Kabardino-Balkariya Republic": "Кабардино-Балкария",
    "Kaliningrad Oblast": "Калининградская обл.",
    "Kalmykiya Republic": "Калмыкия",
    "Kaluga Oblast": "Калужская обл.",
    "Kamchatka": "Камчатский край",
    "Karachayevo-Cherkesiya Republic": "Карачаево-Черкесия",
    "Karelia": "Карелия",
    "Khabarovsk": "Хабаровский край",
    "Khakasiya Republic": "Хакасия",
    "Khanty-Mansia": "Ханты-Мансийский АО",
    "Kirov Oblast": "Кировская обл.",
    "Komi": "Коми",
    "Kostroma Oblast": "Костромская обл.",
    "Krasnodar Krai": "Краснодарский край",
    "Krasnoyarsk Krai": "Красноярский край",
    "Kurgan Oblast": "Курганская обл.",
    "Kursk Oblast": "Курская обл.",
    "Kuzbass": "Кемеровская обл.",
    "Leningradskaya Oblast'": "Ленинградская обл.",
    "Lipetsk Oblast": "Липецкая обл.",
    "Magadan Oblast": "Магаданская обл.",
    "Mariy-El Republic": "Марий Эл",
    "Moscow": "Москва",
    "Moscow Oblast": "Московская обл.",
    "Mordoviya Republic": "Мордовия",
    "Murmansk": "Мурманская обл.",
    "Nenets": "Ненецкий АО",
    "Nizhny Novgorod Oblast": "Нижегородская обл.",
    "North Ossetia–Alania": "Северная Осетия",
    "Novgorod Oblast": "Новгородская обл.",
    "Novosibirsk Oblast": "Новосибирская обл.",
    "Omsk Oblast": "Омская обл.",
    "Orenburg Oblast": "Оренбургская обл.",
    "Oryol oblast": "Орловская обл.",
    "Penza Oblast": "Пензенская обл.",
    "Perm Krai": "Пермский край",
    "Primorye": "Приморский край",
    "Pskov Oblast": "Псковская обл.",
    "Republic of Tyva": "Тыва",
    "Rostov": "Ростовская обл.",
    "Ryazan Oblast": "Рязанская обл.",
    "Sakha": "Якутия",
    "Sakhalin Oblast": "Сахалинская обл.",
    "Samara Oblast": "Самарская обл.",
    "Saratov Oblast": "Саратовская обл.",
    "Smolensk Oblast": "Смоленская обл.",
    "St.-Petersburg": "Санкт-Петербург",
    "Stavropol Kray": "Ставропольский край",
    "Sverdlovsk Oblast": "Свердловская обл.",
    "Tambov Oblast": "Тамбовская обл.",
    "Tatarstan Republic": "Татарстан",
    "Tomsk Oblast": "Томская обл.",
    "Tula Oblast": "Тульская обл.",
    "Tver Oblast": "Тверская обл.",
    "Tyumen Oblast": "Тюменская обл.",
    "Udmurtiya Republic": "Удмуртия",
    "Ulyanovsk": "Ульяновская обл.",
    "Vladimir Oblast": "Владимирская обл.",
    "Volgograd Oblast": "Волгоградская обл.",
    "Vologda Oblast": "Вологодская обл.",
    "Voronezh Oblast": "Воронежская обл.",
    "Yamalo-Nenets": "Ямало-Ненецкий АО",
    "Yaroslavl Oblast": "Ярославская обл.",
    "Zabaykalskiy (Transbaikal) Kray": "Забайкальский край",
}


def _cache_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "dh-geonames-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(name: str, cache: Path) -> Path:
    dest = cache / name
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached {name}", file=sys.stderr)
        return dest
    url = _GEONAMES + name
    req = urllib.request.Request(url, headers={"User-Agent": "dh-cities-loader"})
    print(f"  downloading {url} ...", file=sys.stderr)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)
    tmp.replace(dest)
    return dest


def _ru_alt_names(cache: Path) -> dict[int, str]:
    """geonameid -> best Russian alternate name (preferred > short > plain,
    skipping historic), so Cheboksary reads "Чебоксары" and not the Chuvash
    exonym "Чабаксар"."""
    zip_path = _download("alternateNamesV2.zip", cache)
    best: dict[int, tuple[int, str]] = {}
    with zipfile.ZipFile(zip_path) as z, z.open("alternateNamesV2.txt") as fh:
        for line in io.TextIOWrapper(fh, "utf-8"):
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 4 or cols[2] != "ru":
                continue
            if len(cols) > 7 and cols[7] == "1":  # isHistoric
                continue
            name = cols[3].strip()
            if not name:
                continue
            try:
                gid = int(cols[1])
            except ValueError:
                continue
            prio = 3 if (len(cols) > 4 and cols[4] == "1") else (
                2 if (len(cols) > 5 and cols[5] == "1") else 1
            )
            cur = best.get(gid)
            if cur is None or prio > cur[0]:
                best[gid] = (prio, name)
    print(f"  russian alternate names: {len(best)}", file=sys.stderr)
    return {gid: v[1] for gid, v in best.items()}


def _admin1_map(cache: Path) -> dict[str, str]:
    text = _download("admin1CodesASCII.txt", cache).read_text("utf-8")
    out: dict[str, str] = {}
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2:
            out[cols[0]] = cols[1]
    return out


def _country_map(cache: Path) -> dict[str, str]:
    text = _download("countryInfo.txt", cache).read_text("utf-8")
    out: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 5:
            out[cols[0]] = cols[4]
    return out


def _is_russian(s: str) -> bool:
    # Whole string is Russian letters (+ common punctuation) — rejects Chuvash
    # (Ç, ĕ …) and Ukrainian (і, ї …) Cyrillic that shares А–Я glyphs.
    return bool(s) and bool(re.fullmatch(r"[А-Яа-яЁё0-9 ,.\-'()№]+", s))


def _display_name(
    gid: int, name: str, ascii_name: str, alternates: str, ru_alt: dict[int, str]
) -> str:
    ru = ru_alt.get(gid)
    if ru:
        return ru
    if _is_russian(name):
        return name
    for alt in alternates.split(","):
        alt = alt.strip()
        if _is_russian(alt):
            return alt
    return name or ascii_name


def _rows_from(
    stream: Iterator[str],
    *,
    only_class_p: bool,
    keep_cc: str | None,
    drop_cc: str | None,
    admin1: dict[str, str],
    country: dict[str, str],
    ru_alt: dict[int, str],
    seen_ru_regions: set[str],
) -> Iterator[dict[str, object]]:
    for line in stream:
        cols = line.rstrip("\n").split("\t")
        if len(cols) < 19:
            continue
        cc = cols[8]
        if keep_cc and cc != keep_cc:
            continue
        if drop_cc and cc == drop_cc:
            continue
        if only_class_p and cols[6] != "P":
            continue
        name = cols[1]
        if not name:
            continue
        region_en = admin1.get(f"{cc}.{cols[10]}")
        region: str | None
        country_name: str | None
        if cc == "RU":
            if region_en:
                seen_ru_regions.add(region_en)
            region = _RU_REGION_RU.get(region_en or "")
            country_name = "Россия"
        else:
            region = region_en
            country_name = _COUNTRY_RU.get(cc) or country.get(cc)
        try:
            gid = int(cols[0])
            yield {
                "id": gid,
                "name": _display_name(gid, name, cols[2], cols[3], ru_alt)[:200],
                "name_ascii": (cols[2] or name)[:200],
                "country_code": cc,
                "country": country_name,
                "region": region,
                "lat": float(cols[4]),
                "lng": float(cols[5]),
                "population": int(cols[14] or 0),
            }
        except ValueError:
            continue


def _open_inner(zip_path: Path, inner: str) -> Iterator[str]:
    zf = zipfile.ZipFile(zip_path)
    return (line for line in io.TextIOWrapper(zf.open(inner), "utf-8"))


def build(out: Path) -> None:
    cache = _cache_dir()
    admin1 = _admin1_map(cache)
    country = _country_map(cache)
    ru_alt = _ru_alt_names(cache)
    ru_zip = _download("RU.zip", cache)
    world_zip = _download("cities15000.zip", cache)

    seen_ru_regions: set[str] = set()
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with gzip.open(out, "wt", encoding="utf-8", newline="") as gz:
        writer = csv.DictWriter(gz, fieldnames=_COLUMNS)
        writer.writeheader()
        sources = (
            (
                _open_inner(ru_zip, "RU.txt"),
                {"only_class_p": True, "keep_cc": "RU", "drop_cc": None},
            ),
            (
                _open_inner(world_zip, "cities15000.txt"),
                {"only_class_p": False, "keep_cc": None, "drop_cc": "RU"},
            ),
        )
        for src, kwargs in sources:
            for row in _rows_from(
                src,
                admin1=admin1,
                country=country,
                ru_alt=ru_alt,
                seen_ru_regions=seen_ru_regions,
                **kwargs,
            ):
                writer.writerow(row)
                n += 1
    print(f"wrote {n} cities -> {out}", file=sys.stderr)
    unmapped = sorted(r for r in seen_ru_regions if r not in _RU_REGION_RU)
    if unmapped:
        print(f"RU regions without a Russian mapping ({len(unmapped)}):", file=sys.stderr)
        for r in unmapped:
            print(f"  - {r}", file=sys.stderr)


async def load(src: Path) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.core.db import engine
    from app.models.city import City

    def _batches() -> Iterator[list[dict[str, object]]]:
        with gzip.open(src, "rt", encoding="utf-8", newline="") as gz:
            reader = csv.DictReader(gz)
            batch: list[dict[str, object]] = []
            for row in reader:
                name = row["name"]
                name_ascii = row["name_ascii"]
                batch.append(
                    {
                        "id": int(row["id"]),
                        "name": name,
                        "name_ascii": name_ascii,
                        "search_name": name.lower(),
                        "search_ascii": name_ascii.lower(),
                        "country_code": row["country_code"],
                        "country": row["country"] or None,
                        "region": row["region"] or None,
                        "lat": float(row["lat"]),
                        "lng": float(row["lng"]),
                        "population": int(row["population"] or 0),
                    }
                )
                # asyncpg caps a statement at 32767 bind params; 11 cols/row.
                if len(batch) >= 2500:
                    yield batch
                    batch = []
            if batch:
                yield batch

    total = 0
    async with engine.begin() as conn:
        for batch in _batches():
            stmt = pg_insert(City).values(batch)
            update_cols = {c: stmt.excluded[c] for c in batch[0] if c != "id"}
            stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
            await conn.execute(stmt)
            total += len(batch)
    print(f"loaded/updated {total} cities", file=sys.stderr)


async def backfill() -> None:
    """Match existing free-text user cities to a canonical City by name (exact,
    case-insensitive), preferring Russian places then the most populous."""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.city import City
    from app.models.user import User

    async with SessionLocal() as session:
        users = list(
            await session.scalars(
                select(User).where(User.city.is_not(None), User.city_id.is_(None))
            )
        )
        matched = 0
        for user in users:
            assert user.city is not None
            city = await session.scalar(
                select(City)
                .where(City.search_name == user.city.strip().lower())
                .order_by((City.country_code == "RU").desc(), City.population.desc())
                .limit(1)
            )
            if city is not None:
                user.city_id = city.id
                user.city = city.name
                matched += 1
        await session.commit()
        print(f"backfilled {matched}/{len(users)} users with a city", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/load the GeoNames city list.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, default=_DATA_FILE)
    lo = sub.add_parser("load")
    lo.add_argument("--in", dest="src", type=Path, default=_DATA_FILE)
    sub.add_parser("backfill")
    args = parser.parse_args()

    if args.cmd == "build":
        build(args.out)
    elif args.cmd == "load":
        asyncio.run(load(args.src))
    else:
        asyncio.run(backfill())


if __name__ == "__main__":
    main()
