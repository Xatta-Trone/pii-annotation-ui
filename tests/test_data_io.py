from src.data_io import export_dataset, load_dataset


def test_csv_round_trip_preserves_ids_order_columns_unicode_multiline():
    original = ("crash_id,clean_narrative,weak_pii_entities_json,extra,annotation_status,gold_entities_json,annotator_notes\n"
                '99999999999999999999,"Line one\nJosé",[],keep,COMPLETED,[],done\n'
                '2,Second,[],also,NOT_ANNOTATED,,\n').encode("utf-8")
    frame = load_dataset(original, "input.csv")
    reloaded = load_dataset(export_dataset(frame), "output.csv")
    assert reloaded["crash_id"].tolist() == ["99999999999999999999", "2"]
    assert reloaded["clean_narrative"].iloc[0] == "Line one\nJosé"
    assert list(reloaded.columns) == list(frame.columns)
    assert reloaded["extra"].tolist() == ["keep", "also"]


def test_tsv_round_trip():
    raw = b"crash_id\tclean_narrative\tweak_pii_entities_json\n001\tText\t[]\n"
    frame = load_dataset(raw, "input.tsv")
    reloaded = load_dataset(export_dataset(frame, separator="\t"), "output.tsv")
    assert reloaded.loc[0, "crash_id"] == "001"
    assert reloaded.loc[0, "clean_narrative"] == "Text"
