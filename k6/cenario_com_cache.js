import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 100 },
    { duration: '20s', target: 100 },
    { duration: '5s', target: 0 },
  ],
};

export default function () {
  const PRODUTO_ID = '6a5025d2904dcd23c60bc7e8'; 
  const url = `http://localhost:8000/produtos/${PRODUTO_ID}`;

  const res = http.get(url);

  check(res, {
    'status é 200': (r) => r.status === 200,
  });

  sleep(0.1);
}


import { htmlReport } from 'https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js';

export function handleSummary(data) {
  return {
    "k6/relatorio_com_cache.html": htmlReport(data),
  };
}