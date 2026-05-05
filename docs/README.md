<!-- markdownlint-disable MD024 MD031 MD032 MD036 MD040 -->
# MeDIAuto Studio Docs

이 폴더는 제품 설명, 사용자 안내, 기술 명세, 보안·규제 자료를 역할별로 나누어 보관한다.

## 빠른 길잡이

| 문서 | 대상 | 용도 |
| --- | --- | --- |
| [PRODUCT_BROCHURE.md](PRODUCT_BROCHURE.md) | 의사결정자, 영업, 구매 | 제품 가치와 도입 효과를 설명하는 소개서 |
| [USER_GUIDE.md](USER_GUIDE.md) | 병리의, 연구원, 관리자 | 의도된 사용, 한계, 화면 조작, 운영 절차를 합친 사용자 가이드 |
| [FEATURES.md](FEATURES.md) | 기획, 개발, QA | 구현된 기능과 내부 동작 명세 |
| [SECURITY.md](SECURITY.md) | 보안, IT, 인허가 | 인증, 권한, 암호화, 감사 로그, SaMD 보안 통제 |
| [COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md) | 인허가, QA | IEC 62304, ISO 14971, 21 CFR Part 11 충족 현황 |
| [DATABASE.md](DATABASE.md) | 개발, 운영 | MongoDB 컬렉션, 인덱스, 데이터 관계 |
| [color_match_analysis.md](color_match_analysis.md) | 영상/색 보정 담당자 | Hamamatsu NDP 색 매칭 분석 |

## 읽는 순서

1. 제품을 처음 이해할 때: [PRODUCT_BROCHURE.md](PRODUCT_BROCHURE.md)
2. 실제 사용법을 확인할 때: [USER_GUIDE.md](USER_GUIDE.md)
3. 구현 기능을 검토할 때: [FEATURES.md](FEATURES.md)
4. 보안·규제 근거가 필요할 때: [SECURITY.md](SECURITY.md) → [COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md)
5. 운영·개발 상세가 필요할 때: [DATABASE.md](DATABASE.md), [color_match_analysis.md](color_match_analysis.md)

## 문서 관리 원칙

- 사용자 대상 안내는 [USER_GUIDE.md](USER_GUIDE.md)에 모은다.
- 제품/영업 메시지는 [PRODUCT_BROCHURE.md](PRODUCT_BROCHURE.md)에 둔다.
- 구현 세부와 개발자 설명은 [FEATURES.md](FEATURES.md)로 보낸다.
- 규제·보안 근거는 [SECURITY.md](SECURITY.md)와 [COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md)에 분리한다.
- 같은 내용을 여러 문서에 길게 복사하지 않고, 필요한 곳에서 링크로 연결한다.
