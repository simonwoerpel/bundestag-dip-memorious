from datetime import datetime, timedelta

from banal import ensure_dict, ensure_list
from followthemoney import model
from followthemoney.util import sanitize_text
from furl import furl
from normality import slugify
from servicelayer import env
from servicelayer.cache import make_key

from memorious.operations.aleph import get_api

from .util import aleph_folder


def init(context, data):
    f = furl(context.params["url"])
    if not env.to_bool("FULL_RUN"):
        start_date = env.get("START_DATE") or (datetime.now() - timedelta(
            **ensure_dict(context.params.get("timedelta"))
        )).date().isoformat()
        f.args["f.datum.start"] = start_date
    data["url"] = f.url
    context.emit(data=data)


def parse(context, data):
    res = context.http.rehash(data)

    f = furl(data["url"])
    segment = f.path.segments[-1]
    if segment == "drucksache":
        _parse = _parse_drucksache

    for document in ensure_list(res.json["documents"]):
        detail_data = _parse(document)
        detail_data["tag_key"] = make_key("processed", document["id"])
        if context.check_tag(detail_data["tag_key"]):
            continue
        detail_data["countries"] = ["de"]
        context.emit("download", data={**data, **detail_data, **{"meta": document}})

    # next page
    fu = furl(data["url"])
    if res.json["cursor"] != fu.args.get("cursor"):
        fu.args["cursor"] = res.json["cursor"]
        context.emit("cursor", data={**data, **{"url": fu.url}})


def folders(context, data):
    def _create_folder(name, parent=None):
        return aleph_folder(
            context,
            {
                "file_name": name,
                "foreign_id": slugify(f"{parent or ''}-{name}"),
                "aleph_folder_id": parent,
            },
        )

    # folders
    # base / legislative term / dokumentart / drucksachetyp
    data["aleph_folder_id"] = _create_folder(
        data["meta"]["drucksachetyp"],
        _create_folder(
            data["meta"]["dokumentart"],
            _create_folder(
                f'{data["meta"]["wahlperiode"]}. Wahlperiode',
                _create_folder(data["base"]),
            ),
        ),
    )

    context.emit(data=data)


def enrich(context, data):
    # make document as processed:
    context.set_tag(data["tag_key"], True)

    api = get_api(context)
    if api is None:
        return

    m = data["meta"]

    def get_entities():
        for item in ensure_list(m.get("urheber")):
            yield {
                "body_name": item["titel"],
                "role": "einbringender urheber"
                if item.get("einbringer")
                else "urheber",
                "document_id": data["aleph_id"],
                "date": data["published_at"],
            }
        for item in ensure_list(m.get("ressort")):
            yield {
                "body_name": item["titel"],
                "role": "federführendes ressort"
                if item["federfuehrend"]
                else "ressort",
                "document_id": data["aleph_id"],
                "date": data["published_at"],
            }
        for item in ensure_list(m.get("autoren_anzeige")):
            yield {
                "person_id": item["id"],
                "person_name": item["autor_titel"],
                "summary": item["titel"],
                "document_id": data["aleph_id"],
                "date": data["published_at"],
            }

    entities = []
    for item in get_entities():
        item = {k: sanitize_text(v) for k, v in item.items()}
        mapping = context.params["mapping"]
        mapping["csv_url"] = "/dev/null"
        query = model.make_mapping(mapping)
        if query.source.check_filters(item):
            entities += [e.to_dict() for e in query.map(item).values()]
    api.write_entities(data["aleph_collection_id"], entities)
    context.log.info("Created %s entities" % len(entities))


def _parse_drucksache(document):
    base = None
    if document["herausgeber"] == "BT":
        base = "Bundestag"
    elif document["herausgeber"] == "BR":
        base = "Bundesrat"
    else:
        return
    data = {"base": base}
    data["title"] = " - ".join(
        (
            base,
            document["dokumentnummer"],
            document["drucksachetyp"],
            document["titel"],
        )
    )
    data["published_at"] = document["datum"]
    data["foreign_id"] = document["id"]
    if "urheber" in document:
        data["publisher"] = ", ".join([u["titel"] for u in document["urheber"]])
    else:
        data["publisher"] = document["herausgeber"]
    data["url"] = document["fundstelle"]["pdf_url"]
    return data
