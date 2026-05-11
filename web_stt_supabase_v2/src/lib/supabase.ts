// 한국어 요약:
//   Firestore에서 Supabase로 마이그레이션한 후의 클라이언트 진입점.
//   .env 의 VITE_SUPABASE_URL / VITE_SUPABASE_KEY 를 읽는다 (Vite는 VITE_
//   prefix만 클라이언트 번들에 노출).
//   robot_session 테이블은 단일 행(id='current')으로 운영되며, 모든 read/write
//   는 SESSION_TABLE/SESSION_ID 상수를 사용한다.

import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_KEY as string | undefined;

if (!url || !key) {
  // 빌드 시점이 아니라 런타임에 체크: 개발 중 .env 누락을 즉시 알 수 있게.
  throw new Error(
    "VITE_SUPABASE_URL / VITE_SUPABASE_KEY must be set in .env",
  );
}

export const supabase = createClient(url, key);

// robot_session는 단일 행 운영. 두 상수를 통해 from()/eq()/filter 호출이
// 일관되게 같은 row를 가리키도록 한다.
export const SESSION_TABLE = "robot_session";
export const SESSION_ID = "current";
