"""
Generic writer for a PBIR-legacy report.json (sections -> visualContainers), the format Power BI
Desktop opens from a PBIP. Reused from the author's earlier ODRES portfolio project; the pages of
this project are defined in build_powerbi_project.py.

Canvas 1280 x 720. Style: light grey page, white bordered cards, navy / teal.
Every page: title, synced slicers, footer with the synthetic-data disclosure.
"""
import itertools
import json

NAVY, TEAL, TEAL2, GREY, AMBER, RED, INK, MUTED, BORDER, PAGE_BG = (
    "#0F2340", "#0D9488", "#5EC4B9", "#C9D3DC", "#C7851A", "#B5473A", "#102033", "#607086", "#DCE4EA", "#F6F8FA")

_ids = itertools.count(1)


# --------------------------------------------------------------------------- literals
def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def text(s: str) -> dict:
    return lit("'" + s.replace("'", "''") + "'")


def color(hex_code: str) -> dict:
    return {"solid": {"color": text(hex_code)}}


TRUE, FALSE = lit("true"), lit("false")


# --------------------------------------------------------------------------- fields
class Report:
    def __init__(self, measure_home: dict, slicers, footer):
        self.measure_home = measure_home          # measure name -> table
        self.slicers = slicers                    # [(label, ("c", table, column))]
        self.footer = footer
        self.sections = []

    # a field is ("m", measure) or ("c", table, column)
    def _entity(self, f):
        return self.measure_home[f[1]] if f[0] == "m" else f[1]

    def _prop(self, f):
        return f[1] if f[0] == "m" else f[2]

    def ref(self, f):
        return f"{self._entity(f)}.{self._prop(f)}"

    def _expr(self, f, alias):
        kind = "Measure" if f[0] == "m" else "Column"
        return {kind: {"Expression": {"SourceRef": {"Source": alias}}, "Property": self._prop(f)}}

    def query(self, fields, order_by=None, descending=True):
        aliases, frm = {}, []
        for f in fields + ([order_by] if order_by else []):
            e = self._entity(f)
            if e not in aliases:
                aliases[e] = f"t{len(aliases)}"
                frm.append({"Name": aliases[e], "Entity": e, "Type": 0})
        select, seen = [], set()
        for f in fields:
            r = self.ref(f)
            if r in seen:
                continue
            seen.add(r)
            select.append({**self._expr(f, aliases[self._entity(f)]), "Name": r, "NativeReferenceName": self._prop(f)})
        q = {"Version": 2, "From": frm, "Select": select}
        if order_by:
            q["OrderBy"] = [{"Direction": 2 if descending else 1,
                             "Expression": self._expr(order_by, aliases[self._entity(order_by)])}]
        return q

    # ----------------------------------------------------------------------- visual container
    def container(self, page, x, y, w, h, single_visual):
        z = len(page["visualContainers"]) * 1000
        name = f"{next(_ids):020x}"
        config = {"name": name,
                  "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
                  "singleVisual": single_visual}
        page["visualContainers"].append({"x": x, "y": y, "z": z, "width": w, "height": h,
                                         "config": json.dumps(config), "filters": "[]"})

    def visual(self, page, vtype, x, y, w, h, roles: dict, title=None, objects=None, order_by=None,
               descending=True, card_style=True, slicer_sync=None):
        fields = [f for fs in roles.values() for f in fs]
        projections = {role: [{"queryRef": self.ref(f), **({"active": True} if vtype == "slicer" else {})}
                              for f in fs] for role, fs in roles.items()}
        vc = {}
        if title:
            vc["title"] = [{"properties": {"show": TRUE, "text": text(title), "fontColor": color(INK),
                                           "fontSize": lit("11D"), "bold": TRUE}}]
        else:
            vc["title"] = [{"properties": {"show": FALSE}}]
        if card_style:
            vc["background"] = [{"properties": {"show": TRUE, "color": color("#FFFFFF"), "transparency": lit("0D")}}]
            vc["border"] = [{"properties": {"show": TRUE, "color": color(BORDER), "radius": lit("8D")}}]
            vc["padding"] = [{"properties": {"top": lit("10D"), "bottom": lit("10D"), "left": lit("12D"),
                                             "right": lit("12D")}}]
        sv = {"visualType": vtype, "projections": projections,
              "prototypeQuery": self.query(fields, order_by, descending),
              "drillFilterOtherVisuals": True, "hasDefaultSort": order_by is None,
              "objects": objects or {}, "vcObjects": vc}
        if slicer_sync:
            sv["syncGroup"] = {"groupName": slicer_sync, "fieldChanges": True, "filterChanges": True}
        self.container(page, x, y, w, h, sv)

    def textbox(self, page, x, y, w, h, paragraphs):
        """paragraphs: list of (text, size_pt, bold, color)."""
        paras = [{"textRuns": [{"value": t, "textStyle": {"fontSize": f"{size}pt", "color": col,
                                                          **({"fontWeight": "bold"} if bold else {})}}]}
                 for t, size, bold, col in paragraphs]
        self.container(page, x, y, w, h, {
            "visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {"general": [{"properties": {"paragraphs": paras}}]},
            "vcObjects": {"background": [{"properties": {"show": FALSE}}]}})

    # ----------------------------------------------------------------------- page
    def page(self, title, question):
        p = {"config": json.dumps({"objects": {"background": [{"properties": {"color": color(PAGE_BG),
                                                                              "transparency": lit("0D")}}]}}),
             "displayName": title, "displayOption": 1, "filters": "[]", "height": 720.0,
             "name": f"ReportSection{len(self.sections) + 1}", "ordinal": len(self.sections),
             "visualContainers": [], "width": 1280.0}
        self.sections.append(p)
        self.textbox(p, 12, 4, 660, 66, [(title, 16, True, NAVY), (question, 10, False, MUTED)])
        for i, (label, field) in enumerate(self.slicers):
            self.visual(p, "slicer", 692 + i * 196, 4, 184, 66, {"Values": [field]}, title=label,
                        objects={"data": [{"properties": {"mode": text("Dropdown")}}],
                                 "header": [{"properties": {"show": FALSE}}]},
                        slicer_sync=label.lower())
        self.textbox(p, 16, 694, 1100, 22, [(self.footer, 8, False, MUTED)])
        return p

    def cards(self, page, measures, y=74, h=84):
        n = len(measures)
        gap = 12
        w = (1248 - gap * (n - 1)) / n
        for i, m in enumerate(measures):
            self.visual(page, "card", round(16 + i * (w + gap)), y, round(w), h, {"Values": [("m", m)]},
                        objects={"labels": [{"properties": {"color": color(NAVY), "fontSize": lit("22D")}}],
                                 "categoryLabels": [{"properties": {"color": color(MUTED), "fontSize": lit("9D")}}]})

    def build(self) -> dict:
        return {"config": json.dumps({"version": "5.59", "themeCollection": {}, "activeSectionIndex": 0,
                                      "linguisticSchemaSyncVersion": 0, "objects": {}}),
                "layoutOptimization": 0, "resourcePackages": [], "sections": self.sections}


# --------------------------------------------------------------------------- common chart settings
def bar_objects(fill=TEAL, labels=True, series_colors=None, percent=False):
    obj = {"categoryAxis": [{"properties": {"showAxisTitle": FALSE}}],
           "valueAxis": [{"properties": {"showAxisTitle": FALSE, "show": FALSE if labels else TRUE}}],
           "labels": [{"properties": {"show": TRUE if labels else FALSE, "color": color(INK),
                                      **({"labelPrecision": lit("1L")} if percent else {})}}]}
    if series_colors:
        obj["dataPoint"] = [{"properties": {"fill": color(c)}, "selector": {"metadata": ref}}
                            for ref, c in series_colors.items()]
    else:
        obj["dataPoint"] = [{"properties": {"fill": color(fill)}}]
    return obj
