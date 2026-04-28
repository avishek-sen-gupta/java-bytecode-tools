"""Tests for frames_print pretty-printer."""

from frames_print import _flatten_chain, _format_chain, _format_frame, _format_frames


class TestFlattenChain:
    def test_single_node_no_children(self):
        node = {"method": "A"}
        assert _flatten_chain(node) == [{"method": "A"}]

    def test_two_node_chain(self):
        node = {"method": "A", "children": [{"method": "B"}]}
        assert _flatten_chain(node) == [
            {"method": "A", "children": [{"method": "B"}]},
            {"method": "B"},
        ]

    def test_three_node_chain(self):
        node = {
            "method": "A",
            "children": [{"method": "B", "children": [{"method": "C"}]}],
        }
        result = _flatten_chain(node)
        assert [f["method"] for f in result] == ["A", "B", "C"]


class TestFormatFrame:
    def test_basic_format(self):
        frame = {
            "class": "com.example.Foo",
            "method": "bar",
            "lineStart": 10,
            "lineEnd": 20,
            "sourceLineCount": 11,
        }
        assert _format_frame(frame) == "com.example.Foo.bar  L10-20  (11 lines)"

    def test_missing_fields_use_question_mark(self):
        result = _format_frame({})
        assert "?" in result


class TestFormatChain:
    def test_single_frame_no_callsite(self):
        chain = {
            "class": "A",
            "method": "m",
            "lineStart": 1,
            "lineEnd": 5,
            "sourceLineCount": 5,
        }
        result = _format_chain(0, chain)
        assert "@L" not in result
        assert "Chain 1:" in result

    def test_second_frame_with_callsite_shows_at_L(self):
        chain = {
            "class": "A",
            "method": "m1",
            "lineStart": 1,
            "lineEnd": 10,
            "sourceLineCount": 10,
            "children": [
                {
                    "class": "B",
                    "method": "m2",
                    "lineStart": 20,
                    "lineEnd": 30,
                    "sourceLineCount": 11,
                    "callSiteLine": 7,
                }
            ],
        }
        result = _format_chain(0, chain)
        assert "@L7" in result

    def test_second_frame_without_callsite_no_at_L(self):
        chain = {
            "class": "A",
            "method": "m1",
            "lineStart": 1,
            "lineEnd": 10,
            "sourceLineCount": 10,
            "children": [
                {
                    "class": "B",
                    "method": "m2",
                    "lineStart": 20,
                    "lineEnd": 30,
                    "sourceLineCount": 11,
                }
            ],
        }
        result = _format_chain(0, chain)
        assert "@L" not in result

    def test_root_frame_never_shows_callsite_even_if_field_present(self):
        chain = {
            "class": "A",
            "method": "m",
            "lineStart": 1,
            "lineEnd": 5,
            "sourceLineCount": 5,
            "callSiteLine": 99,
        }
        result = _format_chain(0, chain)
        assert "@L" not in result

    def test_chain_index_in_header(self):
        chain = {
            "class": "A",
            "method": "m",
            "lineStart": 1,
            "lineEnd": 5,
            "sourceLineCount": 5,
        }
        assert "Chain 3:" in _format_chain(2, chain)


class TestFormatFrames:
    def test_not_found(self):
        data = {"toClass": "com.example.Foo", "toLine": 42, "found": False}
        result = _format_frames(data)
        assert "no paths" in result
        assert "com.example.Foo" in result

    def test_found_shows_chain_count(self):
        data = {
            "toClass": "com.example.Foo",
            "toLine": 42,
            "found": True,
            "trace": {
                "children": [
                    {
                        "class": "A",
                        "method": "m",
                        "lineStart": 1,
                        "lineEnd": 5,
                        "sourceLineCount": 5,
                    }
                ]
            },
        }
        result = _format_frames(data)
        assert "1 chain" in result

    def test_from_class_shown_when_present(self):
        data = {
            "fromClass": "com.example.Bar",
            "fromLine": 10,
            "toClass": "com.example.Foo",
            "toLine": 42,
            "found": False,
        }
        result = _format_frames(data)
        assert "com.example.Bar" in result
        assert "line 10" in result
