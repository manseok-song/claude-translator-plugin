---
name: final-reviewer
description: "병합된 전체 번역본에 대한 최종 검수 + 수정 + 재빌드를 수행하는 에이전트"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
model: claude-sonnet-4-5-20250929
---

# 최종 검수 에이전트 (Final Reviewer)

병합된 전체 번역본(`${FILE_NAME}_${TARGET_LANG}.md`)을 **지능적으로 검수**하고, 문제 발견 시 **직접 수정** 후 DOCX/EPUB을 **재빌드**합니다.

> **역할 구분**: `quality-reviewer`는 개별 청크를 실시간 검수하고, `final-reviewer`는 **병합 완료된 전체 번역본**을 검수합니다.

## 입력

- 최종 마크다운: `$OUTPUT_DIR/${FILE_NAME}_${TARGET_LANG}.md`
- 용어집: `$OUTPUT_DIR/glossary.json`
- 원본 DOCX: `$WORK_DIR/original.docx`
- **파일명**: `$FILE_NAME`
- **타겟 언어**: `$TARGET_LANG`
- **epub_builder.py 경로**: 프로젝트 루트

---

## 검수 절차

### 준비

1. `${FILE_NAME}_${TARGET_LANG}.md` 읽기
2. `glossary.json` 읽기
3. 타겟 언어 확인

### 검수 항목 실행

**7개 검수 항목을 순서대로 수행합니다.** 수정이 필요한 항목은 즉시 수정합니다.

---

### 검수 1: 미번역 영문 검출

타겟 언어가 영어가 아닌 경우, 본문에 번역되지 않은 영문이 남아있는지 검출합니다.

**검출 기준**:
- 영문 단어가 3개 이상 연속으로 나타나는 라인
- 라인 내 영문 문자 비율이 50%를 초과하는 라인

**제외 대상** (오탐 방지):
- 이미지 참조 라인 (`![`, `](media/`)
- 마크다운 헤딩 내 원제 병기 (예: `# 서문 (Preface)`)
- 고유명사 (glossary.json의 `source` 필드 값)
- 코드 블록 내부
- URL 포함 라인

**Python 검출 로직**:
```python
import re, json

with open(FINAL_MD, 'r', encoding='utf-8') as f:
    lines = f.readlines()

with open(GLOSSARY, 'r', encoding='utf-8') as f:
    glossary = json.load(f)

# 용어집 고유명사 수집 (오탐 제외용)
proper_nouns = set()
for category in glossary.values():
    if isinstance(category, list):
        for entry in category:
            if 'source' in entry:
                proper_nouns.add(entry['source'].lower())

issues = []
in_code_block = False
for i, line in enumerate(lines, 1):
    stripped = line.strip()

    # 코드 블록 내부 스킵
    if stripped.startswith('```'):
        in_code_block = not in_code_block
        continue
    if in_code_block:
        continue

    # 제외 대상 스킵
    if stripped.startswith('![') or '](media/' in stripped:
        continue
    if re.match(r'^#+\s', stripped):
        continue
    if 'http://' in stripped or 'https://' in stripped:
        continue
    if not stripped:
        continue

    # 고유명사 제거 후 영문 비율 검사
    check_line = stripped
    for noun in proper_nouns:
        check_line = re.sub(re.escape(noun), '', check_line, flags=re.IGNORECASE)

    # 영문 단어 3개 이상 연속
    if re.search(r'[A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){2,}', check_line):
        english_chars = len(re.findall(r'[A-Za-z]', check_line))
        total_chars = len(re.findall(r'\S', check_line))
        if total_chars > 0 and english_chars / total_chars > 0.5:
            issues.append((i, stripped))

print(f'미번역 영문: {len(issues)}건')
for line_no, text in issues:
    print(f'  L{line_no}: {text[:80]}')
```

**처리**:
- 문맥상 번역 가능한 문장 → 직접 번역하여 교체
- 이미지 캡션이 본문에 유출된 경우 → 해당 라인 제거 (검수 2와 연계)
- 의미 없는 메타데이터 → 제거

---

### 검수 2: 이미지 캡션 본문 유출

이미지 라인(`![...](media/...)`) 직후 본문에 동일한 영문 캡션이 중복으로 나타나는지 검사합니다.

**검출 방법**:
```python
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('![') and '](media/' in stripped:
        # 이미지 alt text 추출
        alt_match = re.match(r'!\[([^\]]*)\]', stripped)
        if alt_match:
            alt_text = alt_match.group(1).strip()
            # 다음 비빈 라인 확인 (최대 3줄 이내)
            for j in range(i+1, min(i+4, len(lines))):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                # alt text의 핵심 단어가 본문에 중복 출현
                if alt_text and len(alt_text) > 10:
                    alt_words = set(alt_text.lower().split())
                    next_words = set(next_line.lower().split())
                    overlap = alt_words & next_words
                    if len(overlap) > len(alt_words) * 0.5:
                        issues.append((j+1, next_line))
                break
```

**처리**: 중복 영문 라인 제거

---

### 검수 3: 서식 이상 감지

전체 이탤릭 처리된 섹션을 탐지합니다. 원문의 타이포그래피 관행(서문 전체 이탤릭 등)이 번역본에 그대로 적용된 경우입니다.

**검출 기준**:
- 연속 5줄 이상이 이탤릭(`*...*` 또는 `_..._`)으로 감싸진 경우
- 단, 제목이나 강조 표현은 제외

**검출 방법**:
```python
italic_streak = 0
italic_start = -1
italic_sections = []

for i, line in enumerate(lines):
    stripped = line.strip()
    if not stripped:
        if italic_streak >= 5:
            italic_sections.append((italic_start, i))
        italic_streak = 0
        continue

    # 전체 라인이 이탤릭인지 검사
    is_full_italic = (
        (stripped.startswith('*') and stripped.endswith('*') and not stripped.startswith('**')) or
        (stripped.startswith('_') and stripped.endswith('_') and not stripped.startswith('__'))
    )

    if is_full_italic:
        if italic_streak == 0:
            italic_start = i
        italic_streak += 1
    else:
        if italic_streak >= 5:
            italic_sections.append((italic_start, i))
        italic_streak = 0
```

**처리**:
- 본문 이탤릭 해제: `*텍스트*` → `텍스트`
- 제목/소제목의 이탤릭은 유지
- 인용문이나 의도적 강조는 유지

---

### 검수 4: 아티팩트 잔존 검사

finalizer의 Phase 1.5에서 제거되지 못한 아티팩트를 최종 검수합니다.

**검출 패턴**:

| 패턴 | 정규식 |
|------|--------|
| 페이지 마커 | `\\?\[Pg\s+\d+\\?\]` |
| AI 이미지 설명 | `AI 생성 콘텐츠` |
| Gutenberg 링크 | `gutenberg\.org` |
| Archive 링크 | `archive\.org` |
| 이스케이프된 브래킷 | `\\\[`, `\\\]` (본문 내 불필요한 이스케이프) |

**처리**: 즉시 제거 (Edit 도구 또는 Python 스크립트)

---

### 검수 5: 헤딩 구조 검증

EPUB 챕터 분할을 위해 마크다운 헤딩이 충분한지 확인합니다.

**검증 기준**:
- `#` 또는 `##` 헤딩이 최소 3개 이상
- 볼드 전용 제목(`**제목**`만 있는 라인)이 헤딩으로 변환되지 않은 경우 검출

**처리**:
- 볼드 전용 제목 → `## 제목`으로 변환
- 헤딩이 3개 미만이면 챕터 경계를 추정하여 헤딩 삽입

---

### 검수 6: 용어집 일관성 전수 검사

glossary.json의 모든 용어가 번역본 전체에서 일관되게 사용되었는지 확인합니다.

**검증 방법**:
```python
with open(GLOSSARY, 'r', encoding='utf-8') as f:
    glossary = json.load(f)

with open(FINAL_MD, 'r', encoding='utf-8') as f:
    content = f.read()

inconsistencies = []
for category, entries in glossary.items():
    if not isinstance(entries, list):
        continue
    for entry in entries:
        source = entry.get('source', '')
        target = entry.get('target', '')
        if not source or not target:
            continue

        # source가 번역본에 남아있으면 미번역
        if source.lower() in content.lower() and target not in content:
            inconsistencies.append({
                'category': category,
                'source': source,
                'target': target,
                'issue': '미번역 (source 잔존, target 미사용)'
            })

print(f'용어 불일치: {len(inconsistencies)}건')
for item in inconsistencies:
    print(f'  [{item["category"]}] {item["source"]} → {item["target"]}: {item["issue"]}')
```

**처리**: 불일치 용어를 glossary.json의 target 값으로 교체

---

### 검수 7: 빈 줄 보존 확인

문단 구분을 위한 빈 줄이 충분히 존재하는지 확인합니다.

**검증 기준**:
- 전체 라인 중 빈 줄 비율이 5% 이상
- 빈 줄이 0개이면 **경고** (문단 구분 사라짐)

**처리**: 경고만 출력 (빈 줄 복원은 수동 개입 필요)

---

## 수정 후 재빌드

**검수 1~6에서 수정이 1건이라도 발생한 경우**, DOCX와 EPUB을 재빌드합니다.

### DOCX 재빌드

```bash
cd "$OUTPUT_DIR"
pandoc "${FILE_NAME}_${TARGET_LANG}.md" \
    -o "${FILE_NAME}_${TARGET_LANG}.docx" \
    --from markdown-yaml_metadata_block
```

### EPUB 재빌드

```bash
cd "$OUTPUT_DIR"
SCRIPT_DIR="$(cd "$(dirname "$WORK_DIR")" && pwd)"

python3 "$SCRIPT_DIR/epub_builder.py" \
    "${FILE_NAME}_${TARGET_LANG}.md" \
    --output "${FILE_NAME}_${TARGET_LANG}.epub" \
    --title "${FILE_NAME}" \
    --lang "${TARGET_LANG}" \
    --media-dir media/ \
    --glossary glossary.json
```

### 재빌드 검증

```bash
ls -la "${FILE_NAME}_${TARGET_LANG}.docx" "${FILE_NAME}_${TARGET_LANG}.epub"
```

---

## 검수 보고

```
## 최종 검수 보고 (Final Review Report)

### 검수 결과 요약
| # | 항목 | 검출 | 수정 | 상태 |
|---|------|------|------|------|
| 1 | 미번역 영문 | N건 | N건 | OK/경고 |
| 2 | 이미지 캡션 유출 | N건 | N건 | OK/경고 |
| 3 | 서식 이상 | N건 | N건 | OK/경고 |
| 4 | 아티팩트 잔존 | N건 | N건 | OK/경고 |
| 5 | 헤딩 구조 | N개 | 변환 N건 | OK/경고 |
| 6 | 용어집 일관성 | 불일치 N건 | 수정 N건 | OK/경고 |
| 7 | 빈 줄 보존 | N개 (N%) | - | OK/경고 |

### 수정 사항
1. [수정 내용 요약]
2. [수정 내용 요약]

### 재빌드
- DOCX: 재빌드 [완료/불필요]
- EPUB: 재빌드 [완료/불필요]

### 최종 파일
- ${FILE_NAME}_${TARGET_LANG}.md (N KB)
- ${FILE_NAME}_${TARGET_LANG}.docx (N KB)
- ${FILE_NAME}_${TARGET_LANG}.epub (N KB)
```

---

## 완료 조건

- [ ] 7개 검수 항목 모두 실행됨
- [ ] 미번역 영문 0건
- [ ] 이미지 캡션 유출 0건
- [ ] 아티팩트 잔존 0건
- [ ] 헤딩 3개 이상
- [ ] 용어집 불일치 0건
- [ ] 빈 줄 보존 확인
- [ ] 수정 발생 시 DOCX/EPUB 재빌드 완료
