import easyocr
import cv2
import numpy as np
from math import floor, ceil

def _compute_edge_map(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(gx**2 + gy**2)
    return mag / (mag.max() + 1e-8)


def _crop_box(frame, box):
    pts = np.array(box, dtype=np.int32)
    x0 = max(0, pts[:, 0].min())
    x1 = min(frame.shape[1], pts[:, 0].max())
    y0 = max(0, pts[:, 1].min())
    y1 = min(frame.shape[0], pts[:, 1].max())
    if x1 <= x0 or y1 <= y0:
        return None
    return frame[y0:y1, x0:x1]


def _text_still_present(ref_edge_map, frame, box, threshold=0.75):
    crop = _crop_box(frame, box)
    if crop is None or crop.size == 0:
        return False
    new_edges = _compute_edge_map(crop)
    if new_edges.shape != ref_edge_map.shape:
        new_edges = cv2.resize(
            new_edges.astype(np.float32),
            (ref_edge_map.shape[1], ref_edge_map.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        ).astype(np.float64)
    corr = np.corrcoef(ref_edge_map.flatten(), new_edges.flatten())[0, 1]
    return not np.isnan(corr) and corr > threshold

class _SubtitleFilterer:
    def __init__(self, relative_char_widths):
        # Only english for now
        self.reader = easyocr.Reader(["en"])
        self.results = []
        self.relative_char_widths = relative_char_widths
        self.num_ocr_calls = 0
    
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

    def run_easy_ocr_on_image(self, image):
        results = self.reader.readtext(image)
        self.results = results
        self.num_ocr_calls += 1

    def boxes_from_results(self, word, subtitle_offset):
        """
        Extract bounding boxes for a single profanity word from the most recent
        OCR results (self.results). Avoids re-running OCR when multiple lookups
        are needed for the same frame.
        """
        x, y = subtitle_offset
        boxes = []
        for (box, text, _) in self.results:
            text = text.lower()
            spans = self._find_profanity_span_per_word(word, text)
            for span in spans:
                scaled_box = self._scale_box_to_text_span(box, (x, y), text, span)
                if scaled_box is not None:
                    boxes.append(scaled_box)
        return boxes

    def filter_subtitles(self, image, subtitle_region, text_to_bleep):
        """
        Run main algorithm for filtering subtitles.
        Text to bleep: the profanity that needs to be bleeped
        """
        x, y, w, h = subtitle_region
        ## Only run easy ocr on subtitle region
        self.run_easy_ocr_on_image(image[y: y+h, x: x+w])

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
    

def get_bounding_quads(video_path, bad_word_timestamps, relative_char_widths, subtitle_region = None):    
    filterer = _SubtitleFilterer(relative_char_widths)
    capture = cv2.VideoCapture(video_path)
    fps = capture.get(cv2.CAP_PROP_FPS)
    orig_w = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    bounding_quads = {}  #
    AUDIO_TOLERANCE = 0.2   # Measured in ms
    VIDEO_SCALE_FACTOR = 0.63  # We will scale image down by this amount to improve performance

    # I am assuming sutitles are not printed one character at a time, as is generally the case
    timespans = []  # Effectively the timestamps as a list. Allows timestamps to be ordered

    for timestamp in bad_word_timestamps:
        # Multiplying by 1000 to convert to milliseconds from seconds
        start = 1000 * floor(timestamp['start'] - AUDIO_TOLERANCE)
        end = 1000 * ceil(timestamp['end'] + AUDIO_TOLERANCE)
        timespans.append((timestamp['word'], start, end))

    timespans.sort(key=lambda span: span[1])  # Sort by start times
    found_profanity_per_timestamp = [False] * len(timespans)

    capture.set(cv2.CAP_PROP_POS_MSEC, timespans[0][1])  # Measured in ms
    timespan_index = 0  # Index of the earliest unconfirmed timespan
    N = 6  # We only sample every N frames
    frames_in_sequence = 0  # Used for frame skipping. A sequence is at most n frames

    # cache[timespan_index] = (word, quad_in_scaled_coords, ref_edge_map)
    cache = {}

    while (timespan_index < len(timespans) or cache) and capture.isOpened():
        ret, frame = capture.read()

        frames_in_sequence = (frames_in_sequence + 1) % N
        if frames_in_sequence != 0:
            continue
        
        current_pos_in_video = capture.get(cv2.CAP_PROP_POS_MSEC)

        scaled = cv2.resize(frame, (0, 0), fx=VIDEO_SCALE_FACTOR, fy=VIDEO_SCALE_FACTOR)

        if subtitle_region is not None:
            sx, sy, sw, sh = subtitle_region
            scaled_sub = (
                int(sx * VIDEO_SCALE_FACTOR),
                int(sy * VIDEO_SCALE_FACTOR),
                int(sw * VIDEO_SCALE_FACTOR),
                int(sh * VIDEO_SCALE_FACTOR),
            )
        else:
            scaled_sub = (0, 0, scaled.shape[1], scaled.shape[0])

        sub_x, sub_y = scaled_sub[0], scaled_sub[1]
        boxes_scaled = []
        cache_misses = []

        # Step 1: Verify each cached word is still at its known position.
        for cache_key in list(cache.keys()):
            word, box, ref_edge_map = cache[cache_key]
            if _text_still_present(ref_edge_map, scaled, box):
                boxes_scaled.append(box)
            else:
                cache_misses.append(cache_key)

        # Timespans that are active this frame and not yet found.
        unfound_timestamps = [
            i for i in range(timespan_index, len(timespans))
            if not found_profanity_per_timestamp[i]
            and timespans[i][1] <= current_pos_in_video <= timespans[i][2]
            and i not in cache
        ]

        # Run OCR at most once per frame, only when a cache miss or active
        # timespan requires it (active meaning we found it)
        if cache_misses or unfound_timestamps:
            sub_crop = scaled[
                scaled_sub[1]:scaled_sub[1] + scaled_sub[3],
                scaled_sub[0]:scaled_sub[0] + scaled_sub[2],
            ]
            filterer.run_easy_ocr_on_image(sub_crop)

            # Group misses and active uncached by word. Sort
            # miss_keys descending so the earliest timespan indices are dropped
            # first if OCR finds fewer boxes than expected.
            missed_by_word = {}
            for cache_key in cache_misses:
                word = cache[cache_key][0]
                missed_by_word.setdefault(word, []).append(cache_key)

            uncached_by_word = {}
            for i in unfound_timestamps:
                word = timespans[i][0]
                uncached_by_word.setdefault(word, []).append(i)

            for word in set(missed_by_word) | set(uncached_by_word):
                found = filterer.boxes_from_results(word, (sub_x, sub_y))
                miss_keys = sorted(missed_by_word.get(word, []))
                uncached_idxs = uncached_by_word.get(word, [])

                for k in miss_keys:
                    del cache[k]

                available = list(found)
                for miss_key in miss_keys:
                    if not available:
                        break
                    new_box = available.pop(0)
                    crop = _crop_box(scaled, new_box)
                    if crop is not None and crop.size > 0:
                        cache[miss_key] = (word, new_box, _compute_edge_map(crop))
                        boxes_scaled.append(new_box)

                for ts_i, new_box in zip(uncached_idxs, available):
                    crop = _crop_box(scaled, new_box)
                    if crop is not None and crop.size > 0:
                        cache[ts_i] = (word, new_box, _compute_edge_map(crop))
                        boxes_scaled.append(new_box)
                    found_profanity_per_timestamp[ts_i] = True

        # Expire timespans that ended before we got a chance to find them.
        i = timespan_index
        while i < len(timespans) and timespans[i][1] <= current_pos_in_video:
            if not found_profanity_per_timestamp[i] and current_pos_in_video > timespans[i][2]:
                found_profanity_per_timestamp[i] = True
            i += 1

        # Advance timespan_index past all confirmed/expired timespans.
        while timespan_index < len(timespans) and found_profanity_per_timestamp[timespan_index]:
            timespan_index += 1

        # If cache is empty and we are between timespans, jump directly to the start of the next one.
        if not cache and timespan_index < len(timespans):
            next_start_ms = timespans[timespan_index][1]
            if current_pos_in_video < next_start_ms:
                capture.set(cv2.CAP_PROP_POS_MSEC, next_start_ms)
                continue

        # Scale quads to original resolution and record them against the frame index.
        if boxes_scaled:
            inv = 1.0 / VIDEO_SCALE_FACTOR
            frame_idx = int(capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            quads = [[(int(px * inv), int(py * inv)) for px, py in box] for box in boxes_scaled]
            bounding_quads.setdefault(frame_idx, []).extend(quads)

    capture.release()
    return bounding_quads, fps, (orig_w, orig_h)
