# Takebraid

**촬영 원본을 분석해 필요한 순간을 고르고, 편집 초안으로 엮습니다.**

[English](README.md) · [설계 철학](docs/design-philosophy.ko.md) · [개발 계획](docs/roadmap.md)

대사가 거의 없거나 없는 여러 촬영본에서 중요한 사건을 고르고, 불량 구간을 표시하고,
수정 가능한 컷편집 초안을 만드는 로컬 우선 오픈소스 프로젝트입니다.

## 현재 가능한 것

현재는 **저장소 초기화 단계**입니다. Python 패키지 설치, `takebraid --version`,
`takebraid doctor`, 정확한 원본 시간 표현, 테스트와 CI가 준비되어 있습니다.
영상 분석·자동 구성·렌더링은 아직 구현되지 않았습니다.

첫 목표는 **무대사 작업 과정·제품 촬영본 → 촬영 순서를 유지하는 편집 초안**입니다.
원본은 보존하고, 선택·제외 이유와 대안 테이크를 검토할 수 있도록 개발합니다.

## 개발 시작

Python 3.11 이상을 사용합니다. macOS/Linux:

```bash
git clone https://github.com/swimmingkiim/takebraid.git
cd takebraid
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
takebraid doctor
python -m pytest
```

Windows PowerShell에서는 `python -m venv .venv`와 `.venv\Scripts\Activate.ps1`을 사용합니다.
FFmpeg/ffprobe는 별도로 설치합니다. 현재 기본 테스트에는 모델과 영상 도구가 필요하지 않습니다.
`doctor`는 두 도구 중 하나라도 없으면 종료 코드 1을 반환합니다.

## 개발 방향

1. 원본·시간 정보·편집 결정을 신뢰할 수 있게 만든다.
2. 불량 구간을 표시하고 복원 가능한 제외 기능을 만든다.
3. 행동의 시작·실행·결과를 찾아 중요 구간 후보를 만든다.
4. 순서·길이·중복 조건을 고려해 여러 촬영본을 구성한다.
5. 실제 편집자의 수정 시간과 핵심 장면 손실률로 평가한다.

[시스템 구조](docs/architecture.md), [데이터 계약](docs/contracts.md),
[출시별 완료 조건](docs/roadmap.md), [평가 계획](docs/evaluation.md)을 함께 관리합니다.
프로젝트 코드는 Apache-2.0이며 모델·데이터·외부 도구의 조건은 별도로 관리합니다.
