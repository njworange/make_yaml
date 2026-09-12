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
- 쿠팡플레이: 미해결


######**<OTT별 메모>**

- 웨이브, 티빙: 기존 provider 경로 유지. all season 처리 사용.
- 아마존 프라임 비디오: public detail page 기반으로 title, summary, 시즌/에피소드 정보를 가져온다.
- 애플 TV: public page + 공개 메타데이터 기반으로 동작한다. 다중 시즌 수집까지 반영되어 있다.
- EBSKIDS: 공개 program page와 episode detail page JSON-LD 를 사용한다. episode summary 와 날짜 prefix title 이 반영되어 있다.
- 넷플릭스: public title page 기반 parser 가 추가되어 episode title, summary, 썸네일 추출이 가능하다. 다만 현재 공개 페이지 기준으로 episode 날짜 정보는 확인하지 못했다.
- 디즈니플러스: public parser 기준으로 entity page 의 title, summary, image, year, cast 같은 show-level 메타데이터는 공개되어 있으나, episode/season payload 는 아직 확보하지 못했다. legacy provider 경로는 별도로 남아 있다.
- 쿠팡플레이: 아직 안정적인 public parser 경로를 찾지 못했다.


######**<날짜 prefix 정책>**

최종 YAML의 회차 제목은 provider와 무관하게 export 경계에서 한 번만 형식을 적용한다.

- 방영일과 제목이 있으면: `2025.05.10(토) 에피소드 제목`
- 방영일만 있으면: `2025.05.10(토)` (뒤에 공백 없음)
- 방영일이 없으면: 날짜를 만들지 않고 제목만 출력한다.

날짜는 최종 `originally_available_at` 값만 사용하고 기존 한국어 한 글자 요일 관례를 유지한다.
작품/시즌 제목에는 이 날짜 장식을 적용하지 않는다. Netflix 등 날짜 수집이 없는 경로에도 날짜를 지어내지 않는다.
Wavve/Tving/Prime/AppleTV/EBS의 중간 provider 데이터에서는 날짜 장식을 만들지 않는다.
따라서 코드 테스트 화면의 원본 메타데이터와 최종 YAML의 표시 제목은 다를 수 있다.

레거시 출력에 남은 선두 `YYYY.MM.DD(요일)` 또는 `YYYY-MM-DD(요일)` 장식은 제거 후 현재 날짜로 다시 붙인다.
반복 접두어도 제거하며 제목 안의 일반 숫자/날짜(요일 없는 날짜 포함)는 보존한다.
이 제한된 구문이 실제 제목 자체와 우연히 동일한 경우는 provenance 정보 없이 구별할 수 없다.
한국어 판정도 같은 장식을 제거한 제목과 원래 요약으로 수행한다. 요일만 한국어라고 생성 허용하지 않는다.
기존 마지막 회차 기반 한국어 판정 범위는 유지한다. 제목이 없어도 한국어 요약이 있으면 날짜만인 제목으로 출력 가능하다.

티빙은 provider가 반환한 방영일을 유지한다.
썸네일 URL의 `/YYYYMMDD/`는 방영일 근거가 아니므로 더 이상 날짜 fallback으로 사용하지 않는다.
이 변경은 기존에 저장된 YAML이나 레거시 provider가 이미 반환한 날짜의 출처를 소급 교정하지 않는다.

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
회차 제목의 날짜/제목 결측 조합, 재정규화, 한국어 판정, 생성 명령의 validation 실패 응답도 격리 검증한다.
Writer는 setup stub으로 import하고 provider 함수는 실제 소스 AST에서 격리해 실행한다.
실제 OTT 응답, 계정, `.pyf`, FlaskFarm 또는 외부 YAML 소비자의 통합 검증을 대체하지 않는다.
