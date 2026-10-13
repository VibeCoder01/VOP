"""Named questions for the deliberately synthetic fixture."""
from vop.contracts import AnswerKind, QuestionSpec


def questions() -> tuple[QuestionSpec, ...]:
    return (
        QuestionSpec("red_square", "1", "Is a red square visible?", AnswerKind.BINARY),
        QuestionSpec("background", "1", "What is the background colour?", AnswerKind.CHOICE,
                     choices=(("white", "White background"), ("black", "Black background"))),
        QuestionSpec("brightness", "1", "How bright is the image?", AnswerKind.ORDINAL,
                     levels=("Dark", "Medium", "Bright")),
        QuestionSpec("blue_circle", "1", "Is a blue circle visible?", AnswerKind.BINARY),
        QuestionSpec("green_triangle", "1", "Is a green triangle visible?", AnswerKind.BINARY),
    )


MOCK_ANSWERS = {"red_square": True, "background": "white", "brightness": 2.0,
                "blue_circle": True, "green_triangle": False}
