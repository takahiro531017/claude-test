from app.normalize import clean_display, norm_key, part_key


def test_fullwidth_and_space():
    assert clean_display("　ＡＢＣ－１２３  ") == "ABC-123"
    assert clean_display("a　b   c") == "a b c"


def test_norm_key_ignores_case_and_space():
    assert norm_key("ダミー 商事") == norm_key("ダミー商事")
    assert norm_key("ＡｂＣ") == norm_key("abc")
    assert norm_key("ﾀﾞﾐｰ") == norm_key("ダミー")  # 半角カナ


def test_part_key_absorbs_separators():
    keys = {part_key(x) for x in ["AB-123", "ab 123", "ＡＢ－１２３", "AB‐123", "AB/123", " ab123 "]}
    assert keys == {"ab123"}


def test_part_key_distinguishes_different_numbers():
    assert part_key("AB-123") != part_key("AB-124")
