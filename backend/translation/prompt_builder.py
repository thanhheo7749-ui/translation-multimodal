from backend.translation.contracts import TranslationRequest

def build_fusion_prompt(req: TranslationRequest) -> str:
    """
    Constructs a structured Fusion Prompt incorporating visual entities,
    slide titles, or previous discourse context according to Contract 3.
    """
    lines = [
        "Bạn là chuyên gia dịch thuật video công nghệ Anh - Việt trực tiếp cho hội thảo kỹ thuật."
    ]

    # Visual context section (if available and relevant)
    has_visual = bool(req.slide_title or req.relevant_entities)
    if has_visual:
        visual_parts = []
        if req.slide_title:
            visual_parts.append(f"Tiêu đề slide: \"{req.slide_title}\"")
        if req.relevant_entities:
            visual_parts.append(f"Thuật ngữ then chốt: {', '.join(req.relevant_entities)}")
        lines.append(f"[Ngữ cảnh trên màn hình]: {' | '.join(visual_parts)}")

    # Previous context section (for revision or anaphora resolution)
    if req.action == "REVISE_PREVIOUS" and req.previous_context:
        lines.append(f"[Câu trước liền kề]: \"{req.previous_context}\"")

    # Target speech sentence
    lines.append(f"[Lời nói diễn giả]: \"{req.speech_text}\"")

    # Instruction
    if req.action == "REVISE_PREVIOUS" and req.previous_context:
        lines.append(
            "Nhiệm vụ: Câu hiện tại liên kết chặt chẽ với câu trước. "
            "Hãy dịch câu hiện tại sang tiếng Việt tự nhiên, làm rõ đại từ/chủ ngữ dựa vào ngữ cảnh câu trước, "
            "bảo toàn thuật ngữ công nghệ."
        )
    elif has_visual:
        lines.append(
            "Nhiệm vụ: Dịch câu của diễn giả sang tiếng Việt tự nhiên, phù hợp với ngữ cảnh slide hiển thị, "
            "tuyệt đối giữ nguyên các tên riêng, tên mô hình và thương hiệu công nghệ (ví dụ OPENSHELL, DeepSeek, Qwen)."
        )
    else:
        lines.append(
            "Nhiệm vụ: Dịch câu nói của diễn giả sang tiếng Việt tự nhiên, chính xác ngữ cảnh chuyên ngành."
        )

    lines.append("Bản dịch:")
    return "\n".join(lines)
