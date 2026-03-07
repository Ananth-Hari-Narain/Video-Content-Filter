from content_filter.audio import *
from content_filter.utils import *
from content_filter.video import SubtitleFilterer
import cv2
import matplotlib.pyplot as plt
from matplotlib import patches

def draw_boxes(image, boxes, title="EasyOCR test", output_path=""):
    """Draw bounding boxes on the image and display it."""
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    fig, ax = plt.subplots(1, 1, figsize=(12, 7))
    ax.imshow(image_rgb)
    ax.set_title(title)
    ax.axis("off")

    for box in boxes:
        top_left, top_right, bottom_right, bottom_left = box
        polygon_points = [top_left, top_right, bottom_right, bottom_left]
        polygon = patches.Polygon(
            polygon_points,
            closed=True,
            linewidth=2,
            edgecolor="lime",
            facecolor="none",
        )
        ax.add_patch(polygon)

    plt.tight_layout()

    backend_name = plt.get_backend().lower()
    is_non_interactive = "agg" in backend_name

    if output_path:
        fig.savefig(output_path, bbox_inches="tight", dpi=200)
        print(f"Saved boxed image to: {output_path}")

    if is_non_interactive:
        plt.close(fig)
    else:
        plt.show()

    return fig

if __name__ == "__main__":
    print("Loading profanity list...")
    tmpdir = "temp"
    debug_output_path = "/home/ananth/repos/video-content-filter/data/processed/Image1Processed.png"
    profanity = load_profanity("/home/ananth/repos/video-content-filter/src/content_filter/config/profanity_words.txt", tmpdir)

    relative_char_widths = get_relative_character_widths()
    print("Testing filtering on image")
    img = cv2.imread("/home/ananth/repos/video-content-filter/data/samples/Image1.png")
    subtitle_filterer = SubtitleFilterer(relative_char_widths)
    boxes = subtitle_filterer.filter_subtitles(img, (303, 830, 1327, 175), ["veah", "saw"])
    draw_boxes(img, boxes, output_path=debug_output_path)

    # censor_audio_from_video(
    #     video_path="/home/ananth/repos/video-content-filter/data/raw/example1.mp4",
    #     output_folder="/home/ananth/repos/video-content-filter/data/processed",
    #     profanity_set=load_profanity("/home/ananth/repos/video-content-filter/src/content_filter/config/profanity_words.txt",
    #                                 tmpdir),
    #     tmpdir=tmpdir,
    # )