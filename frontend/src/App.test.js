import { render, screen } from '@testing-library/react';
import { QuestionText } from './App';

test('preserves spaces in a prose question containing math operators', () => {
  render(
    <QuestionText question="Given the matrices A and B shown below, find A - B." />
  );

  expect(
    screen.getByText('Given the matrices A and B shown below, find A - B.')
  ).toBeInTheDocument();
});
