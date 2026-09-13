### YAML 생성 플러그인

다음과 TMDB 에 없는 에피소드 정보를 OTT 에서 직접 가져오기 위한 플러그인이다.

기본적으로 TMDB 에서 메인 포스터, 에피소드별 썸네일, 공개날짜, 배우 등 정보는
IMDB/TMDB 쪽에서 잘 등록되는 경우가 많으므로, 이 플러그인은 한국어 에피소드 정보와 국내 OTT 메타데이터를 직접 가져오는 목적에 가깝다.

가져온 정보가 한글이 아닐 경우 만들지 않는다.


######**<우선순위>**

EBSKIDS 를 제외하고 7개의 OTT 를 원하는 순서대로 넣는다.

원치 않는 OTT 는 빼면 된다.

수동으로 찾을 때만 해당하면, 자동화시 내부자막이 있는 파일은 릴정보에 해당하는 OTT 만 검색한다.

외부자막은 국내 OTT 도 검색할 예정이다.


######**<최소 매칭 점수>**

특수문자를 제외하고 매칭된다.

['로앤 오더: 성범죄 전담반', '로앤 오더 성범죄 전담반] 매칭점수는 100점이다.

['로앤 오더 성범죄 전담반', '로 앤 오더 성범죄 전담반'] 매칭점수는 96점이다.

['전생했더니 슬라임이었던 건에 대하여', '전생했더니 슬라임이었던 건에 대하여 OAD'] 매칭점수는 90점이다.

참고해서 취향대로 정한다. 실제 점수는 소수점이다.


######**<통합검색어>**

쇼의 경우는 영화와 달리 제목이 같은 경우가 거의 없어서 특별한 경우를 제외하면 제목만으로 매칭하는데 큰 문제가 없다.

가십걸 (2007), 가십걸 (2021) 같은 경우를 위해 구분자 `|` 를 이용해 연도 정보를 함께 넣을 수 있다.

웨이브, 티빙의 경우 **시즌 1, 시즌 2, 1기, 2기 모두 시즌 1, 2** 로 생성되도록 제작되었다. 특별한 경우는 어쩔 수 없다.

시즌 2 스페셜 같은 경우는 시즌 0 으로 본다.


######**<코드 입력 예시>**

웨이브 https://www.wavve.com/player/vod?programid=F3501_F35000000015 에서 ***F3501_F35000000015***

티빙 https://www.tving.com/contents/P001565742 에서 ***P001565742***

쿠팡플레이 https://www.coupangplay.com/titles/b2a54eec-da58-4dbd-a078-5a3fb624b78e 에서 ***b2a54eec-da58-4dbd-a078-5a3fb624b78e***

넷플릭스 https://www.netflix.com/title/81519223 에서 ***81519223***

디즈니플러스 시리즈 URL https://www.disneyplus.com/ko-kr/series/big-bet/506cEky88AhL 에서 ***506cEky88AhL***

디즈니플러스 entity URL https://www.disneyplus.com/browse/entity-7867281e-e1fb-4356-8ead-946de2a9a795 에서 ***entity-7867281e-e1fb-4356-8ead-946de2a9a795*** 또는 ***7867281e-e1fb-4356-8ead-946de2a9a795***

아마존 프라임 비디오 https://www.primevideo.com/detail/0N3EDITHIBCK6E9G5PPZZQYOGQ/ref=atv_dl_rdr 에서 ***0N3EDITHIBCK6E9G5PPZZQYOGQ***

애플 TV https://tv.apple.com/kr/show/리에종---liaison/umc.cmc.62t13xacr3mxnit5a40g8tkla 에서 ***umc.cmc.62t13xacr3mxnit5a40g8tkla***

EBSKIDS https://anikids.ebs.co.kr/anikids/program/show/10024440 에서 ***10024440***


######**<현재 지원 상태>**

현재 코드 기준으로 정리하면 아래와 같다.

- 웨이브: episode parser 가능
- 티빙: episode parser 가능
- 아마존 프라임 비디오: public parser 기반 episode parser 가능
- 애플 TV: public parser 기반 episode parser 가능
- EBSKIDS: public parser 기반 episode parser 가능
- 넷플릭스: public parser 기반 episode parser 가능
- 디즈니플러스: public parser 기준 show-level 메타데이터까지만 확인, episode-level parser 는 아직 보류
- 쿠팡플레이: 비로그인 공개 metadata API 기반 시즌/회차 parser (1.0.34부터)


######**<OTT별 메모>**

- 웨이브, 티빙: 기존 provider 경로 유지. all season 처리 사용.
- 아마존 프라임 비디오: public detail page 기반으로 title, summary, 시즌/에피소드 정보를 가져온다.
- 애플 TV: public page + 공개 메타데이터 기반으로 동작한다. 다중 시즌 수집까지 반영되어 있다.
- EBSKIDS: 공개 program page와 episode detail page JSON-LD 를 사용한다. episode summary 와 날짜 prefix title 이 반영되어 있다.
- 넷플릭스: public title page 기반 parser 가 추가되어 episode title, summary, 썸네일 추출이 가능하다. 다만 현재 공개 페이지 기준으로 episode 날짜 정보는 확인하지 못했다.
- 디즈니플러스: public parser 기준으로 entity page 의 title, summary, image, year, cast 같은 show-level 메타데이터는 공개되어 있으나, episode/season payload 는 아직 확보하지 못했다. legacy provider 경로는 별도로 남아 있다.
- 쿠팡플레이: 공개 작품/시즌별 회차 API 사용. 실패 시 미검증 legacy provider로 fallback하지 않는다.

###### **<쿠팡플레이 공개 provider (1.0.34)>**

쿠팡 코드 입력에 작품 UUID 또는 `https://www.coupangplay.com/content/<uuid>` URL을 넣는다.
`/en/content/<uuid>` 및 기존 `/titles/<uuid>`도 지원한다. URL의 query/fragment와 마지막 `/`는
작품 ID에서 제외한다. 다른 호스트나 잘못된 UUID는 요청하지 않는다. 작품 코드는 `KC<uuid>`다.

- `discover.coupangstreaming.com/v1/discover/titles/{id}`와
  `.../{id}/episodes?season={n}`를 사용한다. 이 adapter는 로그인·계정·쿠키·토큰을 직접 다루지 않는다.
  공개 응답은 서비스가 보장한 외부 개발자 API 계약이 아니며 지역/정책/응답 구조 변화로 실패할 수 있다.
- 작품 `title`, `description` 및 `images.poster.url` (없으면 `story-art.url`)을 사용한다.
  포스터는 `[{url: ...}]`, 회차 썸네일은 해당 회차 `images.story-art.url` 문자열이다.
  작품 포스터를 회차 썸네일로 복제하지 않는다. 별도의 시즌 포스터/제목은 만들어내지 않는다.
- TVSHOW는 정수 `seasons`가 1~30일 때만 수집한다. `seasonList`가 있으면 중복 없이 1~N인지
  교차 검증한다. 각 시즌의 응답 `season`/`episode` 및 제공된 `parent_id`를 검증하며 중복 회차 번호,
  중복 회차 ID, 빈 시즌, 시즌 불일치는 부분 결과까지 폐기한다. 특별 시즌/불연속 시즌은 추정하지 않는다.
  회차 번호는 원본 그대로 사용하고(0 허용), API의 역순 응답은 번호 오름차순으로 정렬한다.
- 마지막에 N+1 시즌을 한 번 확인한다. 구조화된 `SeasonNotFound / DI-7011`(HTTP 400) 또는
  HTTP 200의 빈 배열만 종료로 인정한다. 임의 HTTP 400이나 다른 오류를 정상 종료로 취급하지 않는다.
  상한 도달·선언 개수 불일치·미지원 구조에서는 안전하게 실패한다. 별도의 회차 pagination 계약은
  확인되지 않았으므로, 이 검증이 서비스의 전체 과거 회차 제공을 보장하지는 않는다.
- 회차 `title`은 원본 그대로 수집한다(`1회` 등). 최종 YAML에서만 기존 공통 날짜 제목 규칙을 적용한다.
  날짜는 **해당 회차 `published_at`의 달력 날짜**를 기존 `normalize_date`로 검증해 사용한다.
  이것은 쿠팡의 publication 값이지 모든 작품의 최초 TV 방영일과 동일함을 보장하는 값은 아니다.
  기존 정규화 정책대로 timezone 변환 없이 원래 날짜 부분을 사용한다. 작품 최초일/썸네일 날짜를
  회차에 복제하지 않는다. 결측은 생략하고 잘못된 비어 있지 않은 날짜는 전체 조회 실패로 처리한다.
- 영화(`MOVIE`)는 회차 API를 호출하지 않고 상세 조회 한 번만 사용한다. 기존 YAML 소비 경로와의
  호환을 위해 **합성 시즌 1/회차 1**로 영화 제목·설명을 담는다. 실제 API 회차 번호가 있다는 뜻은 아니다.
  영화의 `published_at` 역시 쿠팡 publication 값이며 최초 극장 개봉일을 추정하지 않는다.
  영화 정보가 없어도 TVSHOW 지원과 무관하며 다른 타입은 미지원으로 반환한다.
- 요청별 연결/읽기 timeout은 5초/15초, 재시도·redirect 추적·주기적 polling은 없다.
  TVSHOW는 상세 1회 + N개 시즌 + 종료 확인 1회(최대 32회), 영화는 1회다.
  timeout은 전체 작업의 절대 wall-clock 제한이 아니므로 느린 응답은 추가 시간이 걸릴 수 있다.
  사용자 요청에 따라 실행되지만 기존 자동 처리 경로에서도 선택될 수 있다. 대량/동시 요청은 피한다.
- `COUPANG`을 기존 사용자 검색 우선순위에 적힌 위치 그대로 다시 포함한다. 다른 provider의 순서는
  바꾸지 않으며 제외를 원하면 우선순위에서 빼면 된다. 제목 검색 자체는 기존 OTTCODE에 의존하며
  새 쿠팡 검색 API를 구현한 것은 아니다. 검색된 쿠팡 작품 실패 시 다음 provider를 새로 검색하는
  기능도 추가하지 않는다. 우선 작품 URL/UUID 직접 조회로 확인하는 것이 좋다.
- `enabled=True`로 기존 공통 명령 gate를 통과한다. 다른 provider용 gate는 제거하지 않는다.
  공개 builder가 실패하면 `None`과 안전한 `COUPANG_PUBLIC reason=...` 로그를 남긴다.
  쿠팡 테스트/일반 생성 명령은 `ret=fail`을 반환하고 저장하지 않는다. 원문 응답/예외 텍스트를
  로그에 넣지 않는다. 미검증 `site_coupang.pyf`의 `make_data`로 재시도하지 않는다.

정책 참고: [웹 robots.txt](https://www.coupangplay.com/robots.txt)의 `/api` 금지는
`www.coupangplay.com` 경로 규칙이며 별도 API 호스트의 허가/금지를 대신 증명하지 않는다.
robots.txt 부재나 적은 요청 횟수도 자동수집 허용 또는 차단 없음의 보장은 아니다.
401/403/429 등에서 즉시 실패하고 우회하거나 반복 재시도하지 않는다.

검증 한계: 합성 fixture 검증과 소수 공개 응답 구조 확인은 실제 FlaskFarm 실행, 모든 작품의
회차 완전성·publication 의미·한국어 가용성 또는 앞으로의 차단 여부를 보장하지 않는다.
기존 한국어 gate, `delete_title`, TMDB 보강, `split_season` 설정은 그대로 적용된다.


######**<날짜 prefix 정책>**

최종 YAML의 회차 제목은 provider와 무관하게 export 경계에서 한 번만 형식을 적용한다.

- 방영일과 제목이 있으면: `2025.5.10(토) 에피소드 제목`
- 방영일만 있으면: `2025.5.10(토)` (뒤에 공백 없음)
- 방영일이 없으면: 날짜를 만들지 않고 제목만 출력한다.

날짜는 최종 `originally_available_at` 값만 사용하고 기존 한국어 한 글자 요일 관례를 유지한다.
제목의 날짜 표시는 `YYYY.M.D(요일)`로 연도는 4자리, 월/일은 앞의 0 없이 출력한다(예: `2026.2.10(화)`).
작품/시즌 제목에는 이 날짜 장식을 적용하지 않는다. Netflix 등 날짜 수집이 없는 경로에도 날짜를 지어내지 않는다.
Wavve/Tving/Prime/AppleTV/EBS의 중간 provider 데이터에서는 날짜 장식을 만들지 않는다.
따라서 코드 테스트 화면의 원본 메타데이터와 최종 YAML의 표시 제목은 다를 수 있다.

선두 날짜+요일 장식은 월/일 1~2자리를 모두 인식한다. 새 `YYYY.M.D(요일)` 및 과거의 `YYYY.MM.DD(요일)`/`YYYY-MM-DD(요일)` 장식도 제거 후 현재 날짜로 다시 붙인다.
반복 접두어도 제거하며 제목 안의 일반 숫자/날짜(요일 없는 날짜 포함)는 보존한다.
이 제한된 구문이 실제 제목 자체와 우연히 동일한 경우는 provenance 정보 없이 구별할 수 없다.
한국어 판정도 같은 장식을 제거한 제목과 원래 요약으로 수행한다. 요일만 한국어라고 생성 허용하지 않는다.
기존 마지막 회차 기반 한국어 판정 범위는 유지한다. 제목이 없어도 한국어 요약이 있으면 날짜만인 제목으로 출력 가능하다.

티빙은 provider가 반환한 방영일을 유지한다.
썸네일 URL의 `/YYYYMMDD/`는 방영일 근거가 아니므로 더 이상 날짜 fallback으로 사용하지 않는다.
이 변경은 기존에 저장된 YAML이나 레거시 provider가 이미 반환한 날짜의 출처를 소급 교정하지 않는다.

###### **<티빙 실제 회차 방영일 보강>**

티빙 legacy 조회/기존 제목 정리 후, 날짜가 비어 있는 회차만 `support_site.SupportTving`의
`get_program_programid` / `get_frequency_programid` raw 응답으로 선택적으로 보강한다.
`support_site`는 이미 `info.yaml`에 선언된 필수 플러그인이며, 이 보강은 별도 설정 스위치 없이
가능한 경우에만 적용된다. `metadata` 플러그인을 새 의존성으로 추가하지 않는다.

- 요청한 프로그램 ID와 응답 프로그램 `code`를 확인한다. 기존 작품 코드가 다른 경우 보강하지 않는다.
- 회차 `code`(raw 또는 `KV` 접두어)가 있으면 유일한 코드 일치만 사용한다. 코드가 불일치하면 회차번호로 재시도하지 않는다.
- raw API에서 시즌 번호 필드는 확인되지 않았다. 코드 없는 회차는 **작품 코드가 프로그램과 일치하고,
  로컬 시즌이 하나뿐이며 그 index가 1인 경우에만** `(시즌 1, frequency)`로 매칭한다.
  이는 프로그램별 단일 시즌 표현을 사용하는 제한적인 매핑 관례이지 원격 시즌 번호를 확인했다는 뜻은 아니다.
  다중 시즌·특집 시즌(0)·그 밖의 시즌 번호에서는 코드 없이 날짜를 추정하지 않는다.
- source/target의 중복 코드·중복 회차번호 또는 같은 source를 여러 target이 요구하면 모호한 매칭은 건너뛴다.
- 채택하는 날짜는 회차 `episode.broadcast_date`뿐이다. 8자리 `YYYYMMDD`는 `YYYY-MM-DD`로 변환 후
  기존 export 날짜 검증을 통과해야 한다. 프로그램 `broad_dt`나 이미지 URL의 날짜는 사용하지 않는다.
- 기존의 유효한 날짜, 제목, 요약, 이미지와 시즌/회차 구조는 보존한다. 비어 있지 않은 잘못된 기존 날짜도
  임의로 고치지 않으며 기존 export 검증 정책을 따른다. 새 회차를 추가하는 기능은 아니다.
- 최대 10페이지까지만 요청한다. 정상 종료(`has_more=N`)까지 수집한 결과만 적용한다.
  호출 예외·인증 오류 응답·잘못된 응답 구조·반복 페이지·빈 중간 페이지·상한 도달 시 부분 보강도 취소하고
  원래 데이터를 유지한다. 명시적인 마지막 빈 페이지(`has_more=N`)는 정상 종료로 취급한다.
- adapter 내부의 import/호출 실패는 원래 데이터로 fallback한다. 필수 플러그인 자체가 없을 때의
  FlaskFarm 전체 로딩까지 복구하는 기능은 아니다. 인증 상태는 `support_site`에 맡기며 이 adapter는
  비밀번호·쿠키·토큰을 직접 조회/저장하거나 API 응답·예외 내용을 로깅하지 않는다.

오프라인 fixture 검증은 실제 계정 인증이나 날짜/회차 수의 완전성을 증명하지 않는다.
외부 메서드의 timeout·토큰 갱신·호출 제한은 `support_site` 구현에 의존한다. 페이지 상한은 개별 요청의
실행 시간 제한이 아니므로 live FlaskFarm에서 응답 시간과 실제 매칭률은 별도 확인이 필요하다.

**진단 로그 (1.0.33부터)**

새 버전이 실제 로드된 환경에서 티빙 테스트를 한 번 실행한 뒤, make_yaml의 **로그** 메뉴에서
`TVING_DATE_DIAG`를 찾는다. adapter 호출이 반환될 때 INFO 수준 JSON 한 줄을 남긴다.
INFO 로그가 필터링되거나 adapter 호출 전에 실패한 경우에는 표시되지 않을 수 있다.
로그는 YAML/테스트 결과 JSON에 추가되지 않으며, 날짜 보강 판단·페이지 상한·매칭 규칙도 바꾸지 않는다.

- `reason`: 호출의 최종 결과. `APPLIED`이면 `applied`가 실제 추가한 날짜 개수다.
  `NO_UPDATES`일 때 상세한 건너뛴 이유는 `reason_counts`에 있다.
- `PAGE_CAP_REACHED_DISCARD`: 페이지 10에서도 종료되지 않아 전량 폐기.
  `pages`에는 각 페이지의 번호·행수·검증된 `has_more`만 기록한다.
  빈 중간/반복 페이지는 각각 `EMPTY_PAGE_DISCARD` / `REPEATED_PAGE_DISCARD`다.
- `frequency_scope` / `scope_reason`: API 조회 전 로컬 시즌 구조에서 계산한 회차번호 매칭 가능 여부.
  `NO_SEASON1_SCOPE` / `MULTI_SEASON_SKIPPED`는 **코드 없는 회차의 fallback 제약**이며 코드 매칭까지 금지하지 않는다.
  페이지 상한에 걸려 매칭을 시작하지 못해도 시즌 제약을 함께 확인할 수 있다.
- `local_program_match`와 `program_match`: 로컬/응답 프로그램 코드 일치 여부. 응답 확인 전에는 `program_match=null`.
  `NO_PROGRAM_MATCH`는 응답 코드 검증 실패이지 로그인 실패를 확정하는 메시지가 아니다.
- `season_count`, `seasons`: 보강 전 시즌 수와 위치/숫자 index. 최대 20개만 표시하고 잘리면 `seasons_truncated=true`.
  결측은 `MISSING`, 안전하게 숫자로 표시할 수 없는 값은 `UNREPRESENTED`로 표기하며 원문은 출력하지 않는다.
- `matching_started`, `code_attempts`, `frequency_attempts`, `unique_candidates`: 실제 매칭 단계 진입과 시도/유일 후보 수.
  기존 날짜가 있는 회차도 중복 소유권 검사를 위해 포함한다. 매칭 전에 실패하면 시도 수 0은 정상이다.
  `CODE_MISMATCH`, `NO_CANDIDATE`, `AMBIGUOUS_*`, `DUPLICATE_TARGET`, `SOURCE_REUSED`는 상세 매칭 제약이다.
- `source_date_valid/missing/invalid`: 읽은 raw 회차 날짜의 파싱 결과 수(후에 폐기된 페이지도 포함).
  `DATE_INVALID` / `DATE_MISSING`은 source 날짜 상태, `MATCHED_DATE_UNAVAILABLE`은 매칭 후보의 날짜가 없다는 뜻이다.
  이유별 집계는 서로 배타적이지 않으며, 다른 회차의 문제일 수도 있으므로 `applied`와 함께 해석한다.
- `SUPPORT_SITE_UNAVAILABLE`: import/클래스 접근 실패. `PROGRAM_API_ERROR` / `PAGE_API_ERROR`는 해당 호출 단계의 예외
  (메서드 부재 포함)이며 인증·네트워크 중 무엇이 원인인지는 이 코드만으로 확정하지 않는다.
  `stage`와 `page`는 마지막 도달 위치다. 응답을 못 받은 페이지는 `rows=null, has_more=UNAVAILABLE`로 남는다.
- `INVALID_LOCAL_SHAPE`, `INVALID_PROGRAM_ID`, `LOCAL_PROGRAM_MISMATCH`, `NO_MISSING_DATES`, `NO_SOURCE_ROWS`는
  입력/수집 상태에 따른 조기 종료다. `NO_MISSING_DATES`에는 수정하지 않는 잘못된 기존 비어 있지 않은 날짜도 포함된다.
  잘못된 프로그램/페이지 응답은 `PROGRAM_RESPONSE_INVALID` / `PAGE_RESPONSE_INVALID` /
  `PAGE_RESULT_INVALID` / `PAGE_EPISODE_INVALID`, 그 밖의 처리 예외는 `ENRICHMENT_ERROR`로 구분한다.

로그에 작품/회차 코드, 제목, URL, 실제 날짜 값, 토큰·쿠키·헤더, raw 응답 또는 예외 텍스트를 넣지 않는다.
같은 시각의 다른 요청과 혼동하지 않도록 문제 작품을 한 번씩 재현하고 해당 시각의 한 줄을 확인한다.
logger/진단 처리 실패도 기존 결과를 바꾸지 않는다. 외부 메서드가 반환하지 않는 경우에는 완료 로그도 없으며,
다른 플러그인의 자체 로깅까지 이 adapter가 통제하지는 않는다.

###### **<YAML 출력 정규화>**

TMDB 보강이 끝난 뒤, 파일 저장 직전에 입력 데이터의 복사본을 정규화한다.

- 존재하는 키의 우선순위:
  - 작품: `primary, code, title, posters, seasons`
  - 시즌: `index, posters, title, episodes`
  - 회차: `index, title, summary, thumbs, originally_available_at`
- 기존 `summary`, `extras`, 배우 등의 확장 필드는 core 키 뒤에 보존한다. 회차의 내부 `code` 제거는 기존 정책을 유지한다.
- `title`과 `summary`는 literal block으로 출력한다(일반적으로 `|-`, 빈 문자열은 `''`).
- `posters`: URL 문자열/문자열 목록을 `[{url: URL}]`로 변환한다. 기존 URL 딕셔너리의 부가 정보는 보존한다.
- `thumbs`: 문자열 URL을 사용한다. 목록은 원래 순서에서 첫 번째 사용 가능한 URL을 선택한다.
  이미지 객체는 `url`, 그다음 TMDB art의 `value` 문자열을 사용한다. 작품 포스터로 회차/시즌 이미지를 새로 채우지는 않는다.
- 이미지·날짜가 없으면 생략한다. 이미 존재하는 빈 `posters`는 `[]`로 출력할 수 있다.
- 날짜는 실제 달력상 유효한 `YYYY-MM-DD` 문자열로 출력한다. 입력은 명확한 `YYYY.MM.DD`도 허용한다.
  명시적인 ISO datetime/date 값은 그 값의 날짜 부분을 사용하며 timezone을 변환하지 않는다.
  임의 날짜 문구, 월/일 순서가 모호한 입력, epoch 숫자, URL에서 날짜를 추정하지 않는다.
  알 수 없는 **비어 있지 않은** 이미지 구조나 잘못된 날짜는 임의 변환/삭제하지 않고 `ValueError`로 저장을 중단한다.
  정규화와 직렬화는 대상 파일을 열기 전에 수행한다.
  일반 생성 명령은 이 `ValueError`를 잡아 `ret=fail`과 데이터 형식 오류 안내를 반환한다.
  자동 처리 루프는 기존 항목별 예외 처리/건너뛰기 정책을 유지한다. 다른 모든 오류를 복구하는 기능은 아니다.
- Netflix/Prime/EBS의 누락된 작품 코드는 기존 입력 ID 추출 후 각각 `FN`/`FP`/`KE`를 붙인다.
  AppleTV의 기존 raw ID에는 `FA`를 붙이며 이미 접두어가 있으면 중복 추가하지 않는다.
  다른 provider의 기존 코드 및 Netflix/Prime/EBS가 반환한 비어 있지 않은 코드는 유지한다.
- **기존 설정 우선:** `is_primary=false`이고 `delete_title=true`이면 최상위 제목을 계속 생략한다.
  예시처럼 최상위 제목을 출력하려면 `delete_title`을 끈다. 원본 입력의 제목은 삭제하지 않는다.
- `primary` 의미, 시즌/회차 번호, provider fallback 순서는 변경하지 않는다.
  날짜가 있고 회차 제목이 없을 때 날짜 표시 제목만 추가하며, 제목 내용/시즌/회차를 지어내지는 않는다.
  이 어댑터는 수집 완전성을 보증하는 전체 schema validator가 아니다.
  저장 경로/파일명 정책과 기존 `split_season`의 시즌 메타데이터 손실 문제는 이번 변경 범위에 포함하지 않는다.

###### **<오프라인 검증>**

이번 변경에서 추가한 집중 검증은 다음과 같이 실행한다.

```sh
python3 -B -m unittest discover -s tests -v
```

`tests/test_export_boundary.py`는 합성 fixture로 정규화, 제목 삭제 설정, 코드 주입, 티빙 날짜 처리와 기존 fallback 순서를 검사한다.
쿠팡 builder는 네트워크 함수를 주입해 단일/다중 시즌, 영화, 오류·종료조건·번호·날짜·URL 및 dispatch를 검증한다.
회차 제목의 날짜/제목 결측 조합, 재정규화, 한국어 판정, 생성 명령의 validation 실패 응답도 격리 검증한다.
Writer는 setup stub으로 import하고 provider 함수는 실제 소스 AST에서 격리해 실행한다.
실제 OTT 응답, 계정, `.pyf`, FlaskFarm 또는 외부 YAML 소비자의 통합 검증을 대체하지 않는다.
