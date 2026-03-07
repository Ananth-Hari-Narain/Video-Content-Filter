from typing import Iterable, Optional
import easyocr

class SubtitleFilterer:
    def __init__(self, relative_char_widths):
        # Only english for now
        self.reader = easyocr.Reader(["en"])
        self.results = []
        self.relative_char_widths = relative_char_widths
    
    # Function returns a list of spans as one "word" may contain multiple instances of profanity. E.g. "Yeahyeah" if "yeah" is
    # considered profanity. This can happen as EasyOCR does not always neatly separate words.
    def _find_profanity_span_per_word(
        self,
        profanity_word: str,
        text_to_investigate: str,
    ) -> list[tuple[int, int]]:
        """
        :return: List of tuples where each entry is measured in relative width of characters
        """
        prof_index = 0
        current_x_estimate = 0
        span_start = 0
        spans = []
        for char in text_to_investigate:
            current_x_estimate += self.relative_char_widths[char]
            if char == profanity_word[prof_index] or char == '*':
                prof_index += 1
                if prof_index == len(profanity_word):
                    spans.append((span_start, current_x_estimate))
                    span_start = current_x_estimate
                    prof_index = 0
            else:
                prof_index = 0
                span_start = current_x_estimate

        return spans

    def _scale_box_to_text_span(self, box, full_subtitle_offset, text, span):
        """
        @param box: 4 corner coordinates in EasyOCR format:
                    [top_left, top_right, bottom_right, bottom_left]
        @param full_subtitle_offset: (x_offset, y_offset)  
        @param text: non-empty string that contains the text in the textbox
        @param span: contains the start and end of the swear word in terms of relative character width
        """
        SPAN_BOX_EXPANSION_RATIO = 0.10
        x, y = full_subtitle_offset
        start, end = span
        total_rel_text_length = 0
        for char in text:
            total_rel_text_length += self.relative_char_widths[char]

        start_ratio = start / total_rel_text_length
        end_ratio = end / total_rel_text_length

        span_width_ratio = end_ratio - start_ratio
        pad_ratio = span_width_ratio * SPAN_BOX_EXPANSION_RATIO
        expanded_start_ratio = max(0.0, start_ratio - pad_ratio)
        expanded_end_ratio = min(1.0, end_ratio + pad_ratio)

        top_left, top_right, bottom_right, bottom_left = box

        def _lerp(p1, p2, ratio):
            return (
                p1[0] + (p2[0] - p1[0]) * ratio,
                p1[1] + (p2[1] - p1[1]) * ratio,
            )

        profanity_top_left = _lerp(top_left, top_right, expanded_start_ratio)
        profanity_top_right = _lerp(top_left, top_right, expanded_end_ratio)
        profanity_bottom_left = _lerp(bottom_left, bottom_right, expanded_start_ratio)
        profanity_bottom_right = _lerp(bottom_left, bottom_right, expanded_end_ratio)

        return [
            (int(x + profanity_top_left[0]), int(y + profanity_top_left[1])),
            (int(x + profanity_top_right[0]), int(y + profanity_top_right[1])),
            (int(x + profanity_bottom_right[0]), int(y + profanity_bottom_right[1])),
            (int(x + profanity_bottom_left[0]), int(y + profanity_bottom_left[1])),
        ]

    def _run_easy_ocr_on_image(self, image):
        results = self.reader.readtext(image)
        self.results = results

    def filter_subtitles(self, image, subtitle_region, text_to_bleep):
        """
        Run main algorithm for filtering subtitles.
        Text to bleep: the profanity that needs to be bleeped
        """
        x, y, w, h = subtitle_region
        ## Only run easy ocr on subtitle region
        self._run_easy_ocr_on_image(image[y: y+h, x: x+w])

        boxes = []
        for (box, text, _) in self.results:
            text = text.lower()
            for word in text_to_bleep:
                # Check if text contains profanity (or starred version)
                spans = self._find_profanity_span_per_word(word, text)
                for span in spans:
                    scaled_box = self._scale_box_to_text_span(box, (x, y), text, span)
                    if scaled_box is not None:
                        boxes.append(scaled_box)

        return boxes