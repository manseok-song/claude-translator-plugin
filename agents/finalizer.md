---
name: finalizer
description: "번역본 병합 및 DOCX 빌드를 수행하는 통합 에이전트"
allowed-tools: Read, Write, Bash
model: claude-sonnet-4-5-20250929
---

# 최종화 에이전트 (Finalizer)

번역된 청크들을 **병합**하고 **DOCX 파일**을 생성합니다.

> **주의**: 텍스트 내용을 수정하지 마세요. 병합과 DOCX 생성만 수행합니다.

## 입력

- 번역된 청크들: `$OUTPUT_DIR/translated/translated_*.md`
- 청크 정보: `$OUTPUT_DIR/chunks.json`
- 원본 DOCX: `$WORK_DIR/original.docx`
- 출력: `$OUTPUT_DIR/final.md`, `$OUTPUT_DIR/translated.docx`

---

## Phase 1: 청크 병합

### 작업

chunks.json의 순서대로 번역된 청크들을 하나의 파일로 병합:

```bash
# 청크 순서대로 병합
cat translated/translated_001.md translated/translated_002.md ... > merged.md
```

### 병합 시 주의사항

- 청크 경계에서 문단 연결 자연스럽게
- 중복 제목/헤더 제거
- 일관된 마크다운 형식 유지

---

## Phase 1.5: 마크다운 정리 (DOCX 호환성)

병합된 마크다운에서 DOCX 변환 시 문제를 일으키는 요소를 제거합니다.

```bash
cd "$OUTPUT_DIR"

# 1. 이미지 참조 추가 (맨 앞에)
echo '![표지](media/image1.jpeg)' | cat - merged.md > temp && mv temp merged.md

# 2. 블록 인용(> ) 제거 - DOCX에서 세로 텍스트 문제 유발
sed 's/^> //' merged.md | sed 's/^>$//' > temp && mv temp merged.md

# 3. 백슬래시 줄바꿈(\) 제거
tr -d '\\' < merged.md > temp && mv temp merged.md

# 4. 4칸 들여쓰기 제거 - 코드 블록으로 오인됨
sed 's/^    //' merged.md > temp && mv temp merged.md

# 5. --- 구분선 제거 - YAML 메타데이터로 오인됨
sed '/^---$/d' merged.md > final.md
```

> **중요**: 이 정리 과정을 거치지 않으면 DOCX에서 텍스트가 세로로 늘어지는 문제가 발생합니다.

---

## Phase 2: DOCX 빌드

### 방법 1: pandoc (기본)

```bash
# $OUTPUT_DIR에서 실행해야 media/ 폴더의 이미지가 포함됨
cd "$OUTPUT_DIR"
pandoc "final.md" -o "translated.docx" --from markdown-yaml_metadata_block
```

> **중요**: `media/` 폴더가 `final.md`와 같은 경로에 있어야 이미지가 DOCX에 포함됩니다.

### 방법 2: python-docx (pandoc 실패 시)

```python
from docx import Document

# 원본 스타일 참조
template = Document("original.docx")
doc = Document()

# 스타일 복사 및 텍스트 삽입
# ...
```

### 검증

```bash
# 파일 생성 확인
ls -la translated.docx

# 파일 크기 비교
ls -la original.docx translated.docx
```

---

## 출력 파일

```
$OUTPUT_DIR/
├── merged.md           # 병합된 번역본
├── final.md            # 교정 완료본
└── translated.docx     # 최종 DOCX
```

---

## 완료 보고

```
## 최종화 완료

- 병합된 청크: N개
- 총 문자 수: N자
- 최종 파일: translated.docx (N KB)
```

---

## 완료 조건

- [ ] 모든 청크가 올바른 순서로 병합됨
- [ ] `final.md` 생성됨
- [ ] `translated.docx` 생성됨
