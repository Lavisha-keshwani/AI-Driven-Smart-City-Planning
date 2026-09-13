import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Disclosure, ErrorState, KeyValue, Meter } from './index';
import { ApiError } from '../../api/client';

describe('ErrorState', () => {
  it('shows the backend message and error code', () => {
    render(
      <ErrorState
        error={
          new ApiError('Model 3 (Flood Risk) is not available.', {
            code: 'model_unavailable',
            status: 503,
            detail: { expected_file: 'BEST_MODEL_random_forest.joblib' },
          })
        }
      />,
    );

    expect(screen.getByText(/This model is unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/Model 3 \(Flood Risk\) is not available/)).toBeInTheDocument();
    expect(screen.getByText('model_unavailable')).toBeInTheDocument();
  });

  it('surfaces the remedy the backend suggested', () => {
    render(
      <ErrorState
        error={
          new ApiError('Single-channel image rejected.', {
            code: 'invalid_input',
            status: 400,
            detail: { remedy: 'Upload the R, A and P images.' },
          })
        }
      />,
    );
    expect(screen.getByText('Upload the R, A and P images.')).toBeInTheDocument();
  });

  it('distinguishes an unavailable model from an ordinary failure', () => {
    render(
      <ErrorState error={new ApiError('Bad input.', { code: 'invalid_input', status: 400 })} />,
    );
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
    expect(screen.queryByText(/This model is unavailable/)).not.toBeInTheDocument();
  });

  it('offers a retry when one is given', async () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new ApiError('Boom')} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: /Try again/ }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('renders nothing without an error', () => {
    const { container } = render(<ErrorState error={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('Disclosure', () => {
  it('hides its content until opened', async () => {
    render(
      <Disclosure title="Why the model said this">
        <p>SHAP values</p>
      </Disclosure>,
    );

    expect(screen.queryByText('SHAP values')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Why the model said this/ }));
    expect(screen.getByText('SHAP values')).toBeInTheDocument();
  });

  it('reports its expanded state to assistive technology', async () => {
    render(
      <Disclosure title="Details">
        <p>body</p>
      </Disclosure>,
    );
    const toggle = screen.getByRole('button');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });
});

describe('KeyValue', () => {
  it('says "not available" rather than showing a blank or a zero', () => {
    render(<KeyValue label="Flood probability" value={null} />);
    expect(screen.getByText('not available')).toBeInTheDocument();
  });

  it('renders a real zero as a value', () => {
    render(<KeyValue label="Water occurrence" value={0} />);
    expect(screen.queryByText('not available')).not.toBeInTheDocument();
  });
});

describe('Meter', () => {
  it('clamps out-of-range values instead of overflowing', () => {
    const { container: over } = render(<Meter value={1.7} label="x" />);
    expect(over.querySelector('[style*="width"]')).toHaveStyle({ width: '100%' });

    const { container: under } = render(<Meter value={-0.3} label="y" />);
    expect(under.querySelector('[style*="width"]')).toHaveStyle({ width: '0%' });
  });

  it('shows the percentage', () => {
    render(<Meter value={0.674} label="Flood probability" />);
    expect(screen.getByText('67%')).toBeInTheDocument();
  });
});
