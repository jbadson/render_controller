import pytest

from rendercontroller.util import Config

config_test_dict = {
    "string_val": "val1",
    "int_val": 2,
    "float_val": 3.5,
    "bool_val": True,
}


def test_config_init():
    with pytest.raises(RuntimeError):
        # Make sure we can't instantiate
        Config()


def test_config_set_get():
    conf = Config
    with pytest.raises(RuntimeError):
        conf()  # Make sure we can't instantiate
    conf.set_all(config_test_dict)
    # Test get method
    assert conf.get("string_val") == config_test_dict["string_val"]
    assert conf.get("int_val") == config_test_dict["int_val"]
    assert conf.get("float_val") == config_test_dict["float_val"]
    assert conf.get("bool_val") == config_test_dict["bool_val"]
    # Test subscript method
    assert conf.string_val == config_test_dict["string_val"]
    assert conf.int_val == config_test_dict["int_val"]
    assert conf.float_val == config_test_dict["float_val"]
    assert conf.bool_val == config_test_dict["bool_val"]


def test_config_bad_key():
    conf = Config
    with pytest.raises(AttributeError):
        conf.get("bogus_val")
    with pytest.raises(AttributeError):
        assert conf.bogus_val == True
    assert conf.get("bogus_val", default="something") == "something"