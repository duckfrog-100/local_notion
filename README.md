# Local Notion (사내 오프라인 위키)

Python 표준 라이브러리만으로 실행하는 노션 스타일의 **사내 문서 뷰어/편집기**입니다. 페이지 트리, Markdown 편집/미리보기, 제목·본문 검색, 이미지 업로드 및 페이지 이동을 지원합니다. 외부 CDN이나 인터넷 접속이 필요 없습니다.

> **보안 주의**: 이 저장소는 공개 저장소입니다. 회사 문서, 데이터베이스, 이미지, 비밀번호를 커밋하지 마세요. 실제 업무자료를 개인 PC로 반출하거나 회사 PC로 반입하기 전 사내 보안정책과 정보보호 승인 절차를 따르세요. 노션의 내보내기 제한을 우회하는 수집 기능은 포함하지 않습니다.

## 빠른 실행 (Windows)

1. Python 3.10 이상 설치.
2. 저장소 압축 해제 또는 clone.
3. 관리자 PowerShell에서 **서버가 사용할 로컬 디스크**를 데이터 위치로 설정하는 것을 권장합니다.

```powershell
$env:LOCAL_NOTION_DATA_DIR = "D:\\LocalNotionData"
$env:LOCAL_NOTION_PASSWORD = "강력한-사내-전용-비밀번호"
python app.py
```

4. 웹브라우저에서 `http://127.0.0.1:8765` 접속. 브라우저에서 로그인 창이 뜨면 사용자명은 `staff`, 비밀번호는 `LOCAL_NOTION_PASSWORD` 값입니다. 미설정 시 개발용 localhost 접속만 허용하며, **사내 네트워크 공유 서비스로 사용하지 마세요**.

## 회사 공통 폴더와 연동

이 프로그램은 **한 대의 사내 Windows 서버/PC**에서만 `app.py`를 실행하고, 다른 직원들은 해당 컴퓨터에 브라우저로 접속하는 방식입니다. 직원마다 SQLite DB를 직접 열게 하지 마세요.

```powershell
$env:LOCAL_NOTION_DATA_DIR = "D:\\LocalNotionData" # 권장: 앱 서버의 로컬 디스크
$env:LOCAL_NOTION_ASSETS_DIR = "\\\\fileserver\\Shared\\LocalNotion\\images" # 필요 시 서버 공유폴더의 이미지 경로
$env:LOCAL_NOTION_PASSWORD = "강력한-비밀번호"
$env:LOCAL_NOTION_HOST = "0.0.0.0"
$env:LOCAL_NOTION_PORT = "8765"
python app.py
```

클라이언트에서는 `http://서버PC의-IP:8765` 접속합니다. Windows 방화벽 예외와 서버 보안은 사내 IT 담당자와 협의하세요. **HTTP Basic 인증은 TLS가 없으면 비밀번호가 네트워크에서 노출될 수 있으므로**, 실제 사내 다중 사용자 운영에서는 사내 HTTPS 역방향 프록시 및 사내 인증 체계 적용이 필요합니다. Basic 인증은 개발/시험용 최소 보호장치일 뿐입니다.

- `LOCAL_NOTION_DATA_DIR`: `notion.db` 데이터베이스 및 기본 `assets/` 저장 위치 (기본값: 저장소 옆 `runtime_data/`)
- `LOCAL_NOTION_ASSETS_DIR`: 이미지/첨부파일 저장 위치 선택 지정
- `LOCAL_NOTION_HOST`: 기본값 `127.0.0.1` (로컬만 접속)
- `LOCAL_NOTION_PORT`: 기본값 `8765`
- `LOCAL_NOTION_PASSWORD`: 다중 사용자 네트워크 접근 시 필수

**SQLite 데이터베이스는 SMB/UNC 공유 경로에 두면 잠금 및 파일 손상 위험이 있습니다.** 서버에서 한 프로세스만 실행하고 DB는 해당 서버의 로컬 드라이브에 두는 것을 권장합니다. 파일 서버 폴더에 이미지 보관은 가능하며, DB 백업은 서비스를 정지하거나 SQLite 백업 API를 이용하세요.

## 현재 기능

- 계층형 페이지 트리 / 새 페이지 / 이름 변경 / 삭제 / 이동
- Markdown 본문 편집, 오프라인 미리보기
- 본문/제목 검색
- 페이지 이미지 업로드 (최대 20MB/파일, PNG/JPG/GIF/WebP), 로컬 이미지 표시
- 모든 데이터는 서버 파일 시스템과 SQLite에 저장
- 편집 버전 번호로 동시 저장 충돌 감지 (충돌 시 저장 거절)

## 제한 및 다음 개발

- 노션과 100% 호환되는 에디터가 아니라 **Markdown 기반 MVP**입니다.
- 페이지별 세부 접근권한, 편집 이력, 감사로그, 사용자별 계정, 정교한 멀티유저 충돌 병합 기능이 아직 없습니다.
- Notion API/HTML 가져오기는 **별도 권한 승인 이후** 추가합니다.
- 사내 배포 전 IT 보안 검토, HTTPS, 백업/복구 시험, 인증/권한 관리가 필요합니다.
