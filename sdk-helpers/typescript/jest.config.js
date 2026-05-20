/** @type {import('jest').Config} */
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['<rootDir>/tests/**/*.test.ts'],
  // Coverage thresholds are aspirational; CI smoke test asserts file
  // presence and Jest exit code, not coverage percentage.
  collectCoverage: false,
};
