from typing import Iterable, Optional

import easyocr
from copy import deepcopy


class Trie:
    END = "__end__"

    def __init__(self, words: Optional[Iterable[str]] = None, root = None):
        """
        Pre-requesite: root must be a dictionary of type {str: Trie}.
        If both words and root given, words will be used instead
        """
        self.root = {}
        if words is not None:
            for word in words:
                self.insert(word)

        elif root is not None:
            self.root = deepcopy(root)
            return

    @staticmethod
    def _normalize_word(word):
        return "".join(ch for ch in str(word).lower() if ch.isalpha())

    def insert(self, word):
        normalized_word = self._normalize_word(word)
        if not normalized_word:
            return

        node = self.root
        for ch in normalized_word:
            node = node.setdefault(ch, {})
        node[self.END] = True

    def find_spans(self, normalized_text):
        spans = []
        text_len = len(normalized_text)

        for start in range(text_len):
            frontier = [self.root]
            end = start

            while end < text_len and frontier:
                ch = normalized_text[end]
                next_frontier = []

                if ch == "*":
                    for node in frontier:
                        for edge, child in node.items():
                            if edge != self.END:
                                next_frontier.append(child)
                else:
                    for node in frontier:
                        child = node.get(ch)
                        if child is not None:
                            next_frontier.append(child)

                for node in next_frontier:
                    if self.END in node:
                        spans.append((start, end + 1))

                frontier = next_frontier
                end += 1

        return spans


def _normalize_text_with_map(text: str):
    normalized = []
    index_map = []
    for original_idx, ch in enumerate(text):
        lower_ch = ch.lower()
        if lower_ch.isalpha() or lower_ch == "*":
            normalized.append(lower_ch)
            index_map.append(original_idx)
    return "".join(normalized), index_map


def find_profanity_span_per_word(
    profanity_set: Iterable[str],
    text_words: list[str],
) -> list[Optional[tuple[int, int]]]:
    trie = Trie(words=list(profanity_set))
    cached_results: dict[str, Optional[tuple[int, int]]] = {}
    spans_for_words: list[Optional[tuple[int, int]]] = []

    for text_word in text_words:
        cached_span = cached_results.get(text_word)
        if cached_span is not None or text_word in cached_results:
            spans_for_words.append(cached_span)
            continue

        normalized_text, normalized_to_original_index = _normalize_text_with_map(text_word)
        if not normalized_text:
            cached_results[text_word] = None
            spans_for_words.append(None)
            continue

        normalized_spans = trie.find_spans(normalized_text)
        if not normalized_spans:
            cached_results[text_word] = None
            spans_for_words.append(None)
            continue

        best_start, best_end = min(
            normalized_spans,
            key=lambda span: (span[0], -(span[1] - span[0])),
        )
        original_start = normalized_to_original_index[best_start]
        original_end = normalized_to_original_index[best_end - 1] + 1
        best_span = (original_start, original_end)

        cached_results[text_word] = best_span
        spans_for_words.append(best_span)

    return spans_for_words

class SubtitleFilterer:
    def __init__(self, profanity_set):
        # Only english for now
        self.reader = easyocr.Reader(["en"])
        self.results = []
        self.default_profanity_words = profanity_set
        self.profanity_trie = Trie(words=self.default_profanity_words)

    def _normalize_text_with_map(self, text):
        normalized = []
        index_map = []
        for original_idx, ch in enumerate(text):
            lower_ch = ch.lower()
            if lower_ch.isalpha() or lower_ch == "*":
                normalized.append(lower_ch)
                index_map.append(original_idx)
        return "".join(normalized), index_map

    def _find_profanity_spans(self, text, trie):
        normalized_text, normalized_to_original_index = self._normalize_text_with_map(text)
        if not normalized_text:
            return []

        normalized_spans = trie.find_spans(normalized_text)
        spans = []
        for start, end in normalized_spans:
            original_start = normalized_to_original_index[start]
            original_end = normalized_to_original_index[end - 1] + 1
            spans.append((original_start, original_end))

        if not spans:
            return []

        spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        merged_spans = [spans[0]]
        for span_start, span_end in spans[1:]:
            last_start, last_end = merged_spans[-1]
            if span_start <= last_end:
                merged_spans[-1] = (last_start, max(last_end, span_end))
            else:
                merged_spans.append((span_start, span_end))

        return merged_spans

    def _scale_box_to_text_span(self, box, full_image_offset, text, span):
        if len(box) != 4 or not text:
            return None

        start_idx, end_idx = span
        char_count = len(text)
        if char_count == 0:
            return None

        left_ratio = max(0.0, min(1.0, start_idx / char_count))
        right_ratio = max(0.0, min(1.0, end_idx / char_count))
        if right_ratio <= left_ratio:
            return None

        top_left, top_right, bottom_right, bottom_left = box

        def interpolate(point_a, point_b, ratio):
            return [
                point_a[0] + (point_b[0] - point_a[0]) * ratio,
                point_a[1] + (point_b[1] - point_a[1]) * ratio,
            ]

        span_top_left = interpolate(top_left, top_right, left_ratio)
        span_top_right = interpolate(top_left, top_right, right_ratio)
        span_bottom_left = interpolate(bottom_left, bottom_right, left_ratio)
        span_bottom_right = interpolate(bottom_left, bottom_right, right_ratio)

        x_offset, y_offset = full_image_offset
        translated_box = [
            [span_top_left[0] + x_offset, span_top_left[1] + y_offset],
            [span_top_right[0] + x_offset, span_top_right[1] + y_offset],
            [span_bottom_right[0] + x_offset, span_bottom_right[1] + y_offset],
            [span_bottom_left[0] + x_offset, span_bottom_left[1] + y_offset],
        ]
        return translated_box

    def _run_easy_ocr_on_image(self, image):
        """
        Run EasyOCR on an image
        """
        results = self.reader.readtext(image)
        self.results = results

    def filter_subtitles(self, image, subtitle_region, text_to_bleep):
        """
        Run main algorithm for filtering subtitles
        """
        x, y, w, h = subtitle_region
        ## Only run easy ocr on subtitle region
        self._run_easy_ocr_on_image(image[y: y+h, x: x+w])

        profanity_trie = Trie(text_to_bleep)

        boxes = []
        for (box, text, _) in self.results:
            ## Check if text contains profanity (or starred version)
            spans = self._find_profanity_spans(text, profanity_trie)
            for span in spans:
                scaled_box = self._scale_box_to_text_span(box, (x, y), text, span)
                if scaled_box is not None:
                    boxes.append(scaled_box)

        return boxes