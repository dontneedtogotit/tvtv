// k6 load test: 95% of requests <= 200ms under 1k RPS.
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    streams: {
      executor: 'constant-arrival-rate',
      rate: 1000,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 200,
      maxVUs: 1000,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<200'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

export default function () {
  const res = http.get(`${BASE_URL}/v1/streams`);
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(0.1);
}