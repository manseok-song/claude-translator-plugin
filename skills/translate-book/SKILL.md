# 도서 번역 워크플로우 v3 (Agent Teams)

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

## 아키텍처 v3 (Agent Teams)

```
[original.docx / original.pdf]
       │
       ▼ (PDF인 경우 pdf2docx로 자동 변환)
[original.docx]
       │
       ▼
┌─────────────────────────┐
│   glossary-extractor    │ → glossary.json + guide.md + chunks/
│   (서브에이전트, sonnet) │
└─────────────────────────┘
       │
       ▼ (Team Lead가 TaskCreate로 청크별 작업 생성)
┌─────────────────────────────────────────┐
│          Translation Team               │
│                                         │
│   [Team Lead] ── 작업 생성 + 진행 관리   │
│       │                                 │
│       ├── translator-1 (teammate)       │
│       ├── translator-2 (teammate)       │
│       ├── translator-3 (teammate)       │
│       └── quality-reviewer (teammate)   │
│                                         │
│   Translators: TaskList에서 청크 claim   │
│   → 번역 → completed 처리 → 다음 claim  │
│                                         │
│   Quality Reviewer: 완료된 번역 검수     │
│   → 피드백 → 필요시 재번역 요청          │
└─────────────────────────────────────────┘
       │
       ▼ (모든 번역 태스크 완료 후)
┌─────────────────────────┐
│       finalizer         │ → final.md + .docx + .epub
│   (서브에이전트, sonnet) │
└─────────────────────────┘
       │
       ▼ (병합본 최종 검수)
┌─────────────────────────┐
│     final-reviewer      │ → 검수 + 수정 + 재빌드
│   (서브에이전트, sonnet) │
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

## Step 2: Agent Teams 기반 병렬 번역

### 2-1. 번역 태스크 생성

chunks.json을 읽고, 각 청크에 대해 **TaskCreate**로 태스크를 생성합니다:

```
각 청크에 대해 TaskCreate 호출:
- subject: "번역: chunk_XXX - [청크 제목]"
- description: |
    ## 번역 태스크
    - 청크 파일: $WORK_DIR/output/chunks/chunk_XXX.md
    - 용어집: $WORK_DIR/output/glossary.json
    - 지침서: $WORK_DIR/output/translation_guide.md
    - 타겟 언어: $TARGET_LANG
    - 출력 경로: $WORK_DIR/output/translated/translated_XXX.md

    ## 작업 절차
    1. 청크 파일, glossary.json, translation_guide.md 읽기
    2. 3-in-1 번역 수행 (번역 → 검수 → 의역)
    3. translated_XXX.md 파일 작성
    4. 이 태스크를 completed로 업데이트
- activeForm: "번역 중: chunk_XXX"
```

### 2-2. Translator Teammates 생성

**청크 수에 따라 teammate 수를 결정합니다:**
- 5개 이하: translator 2명 + quality-reviewer 1명
- 6~15개: translator 3명 + quality-reviewer 1명
- 16개 이상: translator 5명 + quality-reviewer 1명

**각 Translator Teammate 생성 시 전달할 프롬프트:**

```
당신은 전문 번역가 팀의 번역 담당입니다.

## 역할
TaskList에서 "번역:" 접두사가 붙은 pending 태스크를 찾아 번역을 수행합니다.

## 작업 루프
1. TaskList로 사용 가능한 번역 태스크 확인
2. pending 상태의 가장 낮은 ID 태스크를 claim (TaskUpdate: status=in_progress, owner=자신)
3. 태스크 description에 명시된 파일들을 읽기
4. .claude/agents/unified-translator.md의 지침에 따라 3-in-1 번역 수행
5. translated_XXX.md 파일 작성 (Write 도구 사용)
6. 태스크를 completed로 업데이트
7. 더 이상 pending 태스크가 없을 때까지 1번으로 돌아감

## 번역 핵심 원칙
- "타겟 언어의 네이티브 작가가 처음부터 쓴 것처럼" 번역
- 용어집 100% 준수
- 번역투 패턴 0건
- 문장마다 자가 검증: "번역서 느낌인가?" → 재작성

## 소통
- 용어집에 없는 중요 용어 발견 시 Team Lead에게 메시지
- 번역 판단이 어려운 문화적 표현은 메시지로 공유

## 중요
- 반드시 .claude/agents/unified-translator.md를 먼저 읽고 상세 지침을 숙지하세요
- glossary.json과 translation_guide.md를 반드시 참조하세요
```

### 2-3. Quality Reviewer Teammate 생성

```
당신은 전문 번역가 팀의 품질 검수 담당입니다.

## 역할
completed 상태의 번역 태스크를 모니터링하고, 번역 품질을 검증합니다.

## 작업 루프
1. TaskList로 completed 상태의 번역 태스크 확인
2. 해당 태스크의 translated_XXX.md와 원본 chunk_XXX.md를 비교 검토
3. 품질 검증 수행:
   - 용어집 일관성 (glossary.json 대조)
   - 번역투 패턴 검출 ("~의" 과다, "~하는 것", "~에 대한" 등)
   - 누락 여부 (원본 대비)
   - 네이티브 자연스러움
4. 심각한 문제 발견 시:
   - 해당 translator에게 메시지로 피드백
   - 문제 태스크를 in_progress로 되돌림 (재번역 요청)
5. 경미한 문제는 직접 수정 (Edit 도구 사용)
6. 모든 번역이 검수 완료되면 Team Lead에게 보고

## 검수 기준
- 반드시 .claude/agents/quality-reviewer.md를 먼저 읽고 상세 기준을 숙지하세요
```

### 2-4. 진행 모니터링

Team Lead는 주기적으로 TaskList를 확인하여 진행 상황을 추적합니다:
- 모든 번역 태스크가 `completed` 상태가 되면 Step 3으로 진행
- 특정 태스크가 오래 걸리면 해당 teammate에게 상태 확인 메시지
- Quality Reviewer의 재번역 요청이 있으면 진행 상황 재확인

**완료 조건**:
- [ ] 모든 `translated_XXX.md` 파일 생성됨
- [ ] 청크 수 = 번역 파일 수
- [ ] Quality Reviewer의 최종 승인

---

## Step 3: 병합 + DOCX/EPUB 빌드

**모든 번역 태스크 완료 후, Task 도구로 `finalizer` 서브에이전트 실행:**

```
서브에이전트에게 전달할 내용:
- 번역된 청크들: $WORK_DIR/output/translated/
- 청크 정보: $WORK_DIR/output/chunks.json
- 원본 DOCX: $WORK_DIR/original.docx
- 파일명: $FILE_NAME
- 타겟 언어: $TARGET_LANG
- epub_builder.py 경로: 프로젝트 루트의 epub_builder.py
- 출력:
  - $WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.md
  - $WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.docx
  - $WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.epub
```

**완료 확인**:
- [ ] `$WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.md` 생성됨
- [ ] `$WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.docx` 생성됨
- [ ] `$WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.epub` 생성됨

---

## Step 3.5: 최종 검수 (Final Review)

**finalizer 완료 후, Task 도구로 `final-reviewer` 서브에이전트 실행:**

병합된 전체 번역본을 지능적으로 검수하여 미번역 영문, 이미지 캡션 유출, 서식 이상, 아티팩트 잔존, 헤딩 구조, 용어집 일관성, 빈 줄 보존을 점검합니다. 수정 발생 시 DOCX/EPUB을 자동 재빌드합니다.

```
서브에이전트에게 전달할 내용:
- 최종 마크다운: $WORK_DIR/output/${FILE_NAME}_${TARGET_LANG}.md
- 용어집: $WORK_DIR/output/glossary.json
- 원본 DOCX: $WORK_DIR/original.docx
- 파일명: $FILE_NAME
- 타겟 언어: $TARGET_LANG
- epub_builder.py 경로: 프로젝트 루트의 epub_builder.py
- 출력 디렉토리: $WORK_DIR/output/
```

**완료 확인**:
- [ ] 7개 검수 항목 모두 실행됨
- [ ] 수정 발생 시 DOCX/EPUB 재빌드 완료
- [ ] 최종 검수 보고 수신

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
    ├── ${FILE_NAME}_${TARGET_LANG}.md    # 최종 병합본
    ├── ${FILE_NAME}_${TARGET_LANG}.docx  # 최종 DOCX
    └── ${FILE_NAME}_${TARGET_LANG}.epub  # 최종 EPUB
```

## 완료 메시지

모든 단계가 완료되면 사용자에게 보고:
- 작업 디렉토리 위치
- 팀 구성 (translator 수, quality reviewer)
- 각 단계별 산출물 목록
- 번역 품질 검수 결과 요약
- 최종 DOCX 파일 경로
- 최종 EPUB 파일 경로
