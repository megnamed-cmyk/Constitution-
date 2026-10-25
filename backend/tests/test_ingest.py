from pathlib import Path

from ingest import conan, constitution
from ingest.common import chunk_paragraphs, provision_from_essay_id, roman_to_int, int_to_roman

FIX = Path(__file__).parent / "fixtures"


def test_roman_roundtrip():
    for n in range(1, 40):
        assert roman_to_int(int_to_roman(n)) == n


def test_provision_from_essay_id():
    assert provision_from_essay_id("artI-S9-C2-1") == ("USConst.Art1.Sec9.Cl2", "Article I > Section 9 > Clause 2")
    assert provision_from_essay_id("ArtII.S2.C2.3.1") == ("USConst.Art2.Sec2.Cl2", "Article II > Section 2 > Clause 2")
    assert provision_from_essay_id("Amdt14.S1.8.1") == ("USConst.Amend14.Sec1", "Amendment XIV > Section 1")
    assert provision_from_essay_id("Intro.1")[1] == "Constitution (general)"


def test_chunk_paragraphs_packs_and_overlaps():
    paras = [("w " * 100).strip() for _ in range(5)]
    chunks = chunk_paragraphs(paras, target_words=320, overlap=1)
    # [p1 p2 p3] then [p3 p4 p5]: paragraph 3 carried forward as overlap
    assert [c.count("\n\n") + 1 for c in chunks] == [3, 3]
    assert all(len(c.split()) <= 320 for c in chunks)


def test_chunk_paragraphs_no_trailing_duplicate():
    assert chunk_paragraphs(["a b c"], target_words=2) == ["a b c"]


def test_constitution_clauses():
    lines = [l for l in (FIX / "constitution_excerpt.txt").read_text().splitlines() if l.strip()]
    chunks = {c.clause_path: c for c in constitution.units_to_chunks(constitution.parse_lines(lines))}
    assert set(chunks) == {
        "USConst.Preamble", "USConst.Art1.Sec1", "USConst.Art1.Sec9.Cl1", "USConst.Art1.Sec9.Cl2",
        "USConst.Art7", "USConst.Amend1", "USConst.Amend14.Sec1",
    }
    habeas = chunks["USConst.Art1.Sec9.Cl2"]
    assert habeas.provision == "Article I > Section 9 > Clause 2"
    assert "Habeas Corpus" in habeas.text and habeas.tier == 1


def test_conan_essay_parse():
    html = (FIX / "conan_essay.html").read_text()
    url = "https://constitution.congress.gov/browse/essay/artI-S9-C2-1/ALDE_00000001/"
    chunks = conan.parse_essay(html, "artI-S9-C2-1", url)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.provision == "Article I > Section 9 > Clause 2"
    assert c.subtopic == "Habeas Corpus Suspension and Separation of Powers"
    assert "Boumediene v. Bush" in c.controlling_precedents and "Ex parte Milligan" in c.controlling_precedents
    assert "footnote paragraph" not in c.text  # footnotes excluded from passage text
    assert "Merryman" not in c.text


def test_conan_discovery_pattern():
    m = conan._ESSAY_HREF.match("/browse/essay/amdt14-S1-8-1/ALDE_00000812/")
    assert m and m["eid"] == "amdt14-S1-8-1"
