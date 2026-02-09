# Claude Translator Plugin

DOCX/PDF 도서를 다국어로 번역하는 Claude Code 플러그인입니다.

## 특징

- **Agent Teams 기반**: v3 아키텍처 - 팀 에이전트 협업으로 번역 품질 극대화
- **다국어 지원**: 한국어, 영어, 일본어, 중국어, 스페인어, 프랑스어, 독일어
- **DOCX + PDF 지원**: PDF 입력 시 자동으로 DOCX 변환 후 번역
- **병렬 팀 번역**: Translator Teammates가 청크를 자동 claim하여 병렬 번역
- **실시간 품질 검수**: Quality Reviewer Teammate가 완료된 번역을 즉시 검수
- **팀 소통**: Teammates 간 용어/문맥 공유로 일관성 보장
- **품질 보장**: 용어집 + 번역 지침서 + Quality Gate 기반 다중 검증
- **이미지 보존**: 원본의 이미지를 번역본에 유지

## 설치

### Claude Code 설정에 플러그인 추가

`~/.claude/settings.json`:

```json
{
  "plugins": [
    "github:manseok-song/claude-translator-plugin"
  ]
}
```

### 의존성

- **pandoc** >= 2.0.0 (DOCX ↔ Markdown 변환)
- **python3** >= 3.8.0
- **pdf2docx** >= 0.5.0 (PDF 입력 시 필요)
- **ebooklib** >= 0.18 (EPUB 빌드)

```bash
# pandoc 설치
brew install pandoc          # macOS
sudo apt install pandoc      # Ubuntu/Debian
choco install pandoc         # Windows

# pdf2docx 설치 (PDF 지원)
pip install pdf2docx

# ebooklib 설치 (EPUB 빌드)
pip install ebooklib
```

## 사용법

```bash
/translate-book <파일경로> [타겟언어]
```

### 예시

```bash
/translate-book book.docx ko        # DOCX → 한국어
/translate-book book.pdf en         # PDF → 영어 (자동 변환)
/translate-book book.docx en        # DOCX → 영어
/translate-book book.pdf ko         # PDF → 한국어
/translate-book book.docx ja        # DOCX → 일본어
```

### 지원 파일 형식

| 형식 | 처리 방식 |
|------|----------|
| `.docx` | 직접 처리 |
| `.pdf` | pdf2docx로 DOCX 변환 후 처리 |

### 지원 언어 코드

| 코드 | 언어 |
|------|------|
| ko | 한국어 |
| en | 영어 |
| ja | 일본어 |
| zh | 중국어 |
| es | 스페인어 |
| fr | 프랑스어 |
| de | 독일어 |

## 아키텍처 (v3 - Agent Teams)

```
[original.docx / original.pdf]
       │
       ▼ (PDF → DOCX 자동 변환)
[original.docx]
       │
       ▼
┌─────────────────────────┐
│   glossary-extractor    │ → glossary.json + guide.md + chunks/
│   (서브에이전트)          │
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
│   Quality Reviewer: 완료된 번역 검수     │
└─────────────────────────────────────────┘
       │
       ▼ (모든 번역 + 검수 완료 후)
┌─────────────────────────┐
│       finalizer         │ → final.md + .docx + .epub
│   (서브에이전트)          │
└─────────────────────────┘
```

### 에이전트 구성

| 에이전트 | 유형 | 역할 |
|---------|------|------|
| `glossary-extractor` | 서브에이전트 | 용어집 + 번역 지침서 + 청크 분할 |
| `unified-translator` | Teammate | TaskList 기반 청크 번역 (번역 + 검수 + 의역) |
| `quality-reviewer` | Teammate | 완료된 번역 실시간 검수 + 피드백 |
| `finalizer` | 서브에이전트 | 병합 + 마크다운 정리 + DOCX/EPUB 빌드 |

### v2 대비 개선점

| 항목 | v2 (서브에이전트) | v3 (Agent Teams) |
|------|-----------------|-----------------|
| 번역 실행 | Task 도구 병렬 호출 | Teammates 자율 claim |
| 품질 검수 | 번역자 자가 검수만 | Quality Reviewer 별도 검수 |
| 팀 소통 | 없음 (독립 실행) | 메시지 기반 실시간 공유 |
| 용어 일관성 | glossary.json만 참조 | 실시간 피드백 + 교차 검증 |
| 에러 처리 | 실패 시 재실행 | 태스크 되돌림 + 재번역 |

## 출력 파일

```
BLACK_HAWK_WAR_ko/                    # 원본파일명_언어코드
├── original.docx                     # 원본
└── output/
    ├── source.md                     # 원본 텍스트
    ├── media/                        # 원본 이미지
    ├── chunks.json                   # 청크 분할 정보
    ├── chunks/                       # 원본 청크
    ├── translated/                   # 번역 청크
    ├── glossary.json                 # 용어집
    ├── translation_guide.md          # 번역 지침서
    ├── BLACK_HAWK_WAR_ko.md          # 최종 병합본
    ├── BLACK_HAWK_WAR_ko.docx        # 최종 DOCX
    └── BLACK_HAWK_WAR_ko.epub        # 최종 EPUB
```

## 번역 원칙

**"타겟 언어의 네이티브 작가가 처음부터 쓴 것처럼"**

- 직역 금지, 의역 우선
- 번역투 표현 제거
- 문화적 맥락 고려
- 캐릭터별 말투 일관성 유지

## 라이선스

MIT License
