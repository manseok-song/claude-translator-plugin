# 도서 번역 워크플로우 v2

**사용법**:
```
/translate-book <파일경로> [타겟언어]
```

**예시**:
```bash
/translate-book book.docx ko        # DOCX → 한국어
/translate-book book.pdf ko         # PDF → 한국어 (자동 변환)
/translate-book book.docx en        # → 영어
/translate-book book.docx ja        # → 일본어
/translate-book book.pdf zh         # PDF → 중국어
```

**입력**: {{ARGS}}

## 인자 파싱

```
{{ARGS}}를 파싱하여:
- FILE_PATH: 첫 번째 인자 (DOCX 또는 PDF 파일 경로)
- TARGET_LANG: 두 번째 인자 (없으면 기본값 "ko")
- FILE_EXT: 파일 확장자 (.docx 또는 .pdf)
- FILE_NAME: 파일명에서 확장자 제거 (예: "BLACK HAWK WAR.docx" → "BLACK_HAWK_WAR")
  - 공백은 언더스코어(_)로 치환
  - 특수문자 제거

지원 파일 형식: .docx, .pdf
지원 언어 코드:
- ko: 한국어 (Korean)
- en: 영어 (English)
- ja: 일본어 (Japanese)
- zh: 중국어 (Chinese)
- es: 스페인어 (Spanish)
- fr: 프랑스어 (French)
- de: 독일어 (German)
```

## 작업 디렉토리 설정

```bash
# 확장자 감지
FILE_EXT="${FILE_PATH##*.}"   # docx 또는 pdf

# 파일명 추출 (확장자 제거, 공백→언더스코어)
FILE_NAME=$(basename "$FILE_PATH" ".$FILE_EXT" | tr ' ' '_' | tr -cd '[:alnum:]_-')

# 작업 디렉토리 생성 (파일명_언어코드 형식)
WORK_DIR="./${FILE_NAME}_${TARGET_LANG}"
mkdir -p "$WORK_DIR"/{output,temp}
```

## PDF 변환 (PDF 입력 시에만)

```bash
# PDF인 경우 → DOCX로 자동 변환
if [ "$FILE_EXT" = "pdf" ]; then
    cp "$FILE_PATH" "$WORK_DIR/original.pdf"
    python3 -c "
from pdf2docx import Converter
cv = Converter('$WORK_DIR/original.pdf')
cv.convert('$WORK_DIR/original.docx')
cv.close()
"
    echo "PDF → DOCX 변환 완료"
else
    cp "$FILE_PATH" "$WORK_DIR/original.docx"
fi
```

> **참고**: PDF 변환에는 `pdf2docx` 패키지가 필요합니다. 없으면 자동 설치: `pip install pdf2docx`

## 아키텍처 v2 (토큰 효율적)

```
[original.docx / original.pdf]
       │
       ▼ (PDF인 경우 pdf2docx로 자동 변환)
[original.docx]
       │
       ▼
┌─────────────────────────┐
│   glossary-extractor    │ → glossary.json + guide.md + chunks/
│       (sonnet)          │
└─────────────────────────┘
       │
       ▼ (병렬 실행)
┌─────────────────────────┐
│  unified-translator x N │ → translated_001.md, 002.md, ...
│       (sonnet)          │    (청크별 병렬 처리)
└─────────────────────────┘
       │
       ▼
┌─────────────────────────┐
│       finalizer         │ → final.md + translated.docx
│       (sonnet)          │
└─────────────────────────┘
```

---

## Step 1: 용어집 + 청크 분할

**Task 도구로 `glossary-extractor` 서브에이전트 실행:**

```
서브에이전트에게 전달할 내용:
- 원본 파일: $WORK_DIR/original.docx
- 출력 위치: $WORK_DIR/output/
- 타겟 언어: $TARGET_LANG
- 작업: 용어집(glossary.json), 번역 지침서(translation_guide.md), 청크 분할(chunks/)
```

**완료 확인**:
- [ ] `$WORK_DIR/output/glossary.json` 존재
- [ ] `$WORK_DIR/output/translation_guide.md` 존재
- [ ] `$WORK_DIR/output/chunks/` 디렉토리에 청크 파일들 존재
- [ ] `$WORK_DIR/output/chunks.json` 존재

---

## Step 2: 청크별 병렬 번역

**Task 도구로 `unified-translator` 서브에이전트를 청크별로 병렬 실행:**

```
각 청크에 대해:
- 청크 파일: $WORK_DIR/output/chunks/chunk_XXX.md
- 용어집: $WORK_DIR/output/glossary.json
- 지침서: $WORK_DIR/output/translation_guide.md
- 타겟 언어: $TARGET_LANG
- 출력: $WORK_DIR/output/translated/translated_XXX.md
- 작업: 번역 + 검수 + 의역 (통합 처리)
```

**병렬 처리 전략**:
- 10개 이하: 한 번에 모두 병렬 실행
- 10개 초과: 10개씩 배치로 나누어 실행

**완료 확인**:
- [ ] 모든 `translated_XXX.md` 파일 생성됨
- [ ] 청크 수 = 번역 파일 수

---

## Step 3: 병합 + DOCX 빌드

**Task 도구로 `finalizer` 서브에이전트 실행:**

```
서브에이전트에게 전달할 내용:
- 번역된 청크들: $WORK_DIR/output/translated/
- 청크 정보: $WORK_DIR/output/chunks.json
- 원본 DOCX: $WORK_DIR/original.docx
- 파일명: $FILE_NAME
- 타겟 언어: $TARGET_LANG
- 출력: $WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.md, $WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.docx
```

**완료 확인**:
- [ ] `$WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.md` 생성됨
- [ ] `$WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.docx` 생성됨

---

## 핵심 번역 원칙

**"타겟 언어의 네이티브 작가가 처음부터 쓴 것처럼"** - 직역 금지, 의역 우선

### 한국어 번역 시 금지 패턴
- "~의" 과다 사용
- "~하는 것"
- "~에 대한/대해"
- "그녀는/그는" (이름이나 생략 사용)

### 영어 번역 시 주의
- Konglish 금지
- 관사/시제 정확성
- Show don't tell

### 일본어 번역 시 주의
- 경어 레벨 통일 (である体/です体)

---

## 최종 산출물

```
${FILE_NAME}_${TARGET_LANG}/          # 예: BLACK_HAWK_WAR_ko/
├── original.docx                     # 원본 파일
└── output/
    ├── source.md                     # 원본 텍스트
    ├── media/                        # 원본 이미지
    ├── chunks.json                   # 청크 분할 정보
    ├── chunks/                       # 원본 청크 파일들
    ├── translated/                   # 번역된 청크 파일들
    ├── glossary.json                 # 용어집
    ├── translation_guide.md          # 번역 지침서
    ├── ${FILE_NAME}_${TARGET_LANG}.md    # 최종 병합본 (예: BLACK_HAWK_WAR_ko.md)
    └── ${FILE_NAME}_${TARGET_LANG}.docx  # 최종 DOCX (예: BLACK_HAWK_WAR_ko.docx)
```

## 완료 메시지

모든 단계가 완료되면 사용자에게 보고:
- 작업 디렉토리 위치
- 각 단계별 산출물 목록
- 최종 DOCX 파일 경로
