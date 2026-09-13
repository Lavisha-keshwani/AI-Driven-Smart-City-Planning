import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import CitySelector from './CitySelector';

/**
 * Regression cover for two bugs this component had:
 *
 *  - the open menu was painted underneath the Leaflet map, because its z-index
 *    (20) was far below Leaflet's panes (400) and controls (1000);
 *  - with 45 cities and no height cap, the menu was ~1800px tall and ran off the
 *    bottom of the viewport.
 *
 * jsdom does not do layout, so the height is asserted through the classes that
 * cap and scroll it; the painted stacking order is covered by the browser smoke
 * test. Both are still worth pinning here so the classes cannot be dropped.
 */

const CITIES = [
  { id: 'Agra', name: 'Agra', state: 'Uttar Pradesh' },
  { id: 'Chennai', name: 'Chennai', state: 'Tamil Nadu' },
  { id: 'Mumbai', name: 'Mumbai', state: 'Maharashtra' },
  { id: 'Kochi', name: 'Kochi', state: 'Kerala' },
];

const SELECTED = CITIES[0];

function open() {
  return userEvent.click(screen.getByRole('button', { expanded: false }));
}

describe('stacking above the map', () => {
  it('puts the selector in its own stacking context above the map', () => {
    const { container } = render(
      <CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />,
    );
    // Leaflet panes sit at z-400 and its controls at z-1000, so the selector must
    // establish a context that is ordered above the map container.
    expect(container.firstChild).toHaveClass('relative', 'z-30');
  });

  it('raises the open menu above its own context', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    const menu = screen.getByRole('listbox').closest('div.absolute');
    expect(menu.className).toMatch(/\bz-50\b/);
  });
});

describe('menu size', () => {
  it('caps the list height and makes it scroll', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    const list = screen.getByRole('listbox');
    expect(list.className).toMatch(/max-h-/);
    expect(list.className).toMatch(/overflow-y-auto/);
  });
});

describe('filtering', () => {
  it('offers a filter that reports the total', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    expect(screen.getByPlaceholderText(/Search 4 cities/)).toBeInTheDocument();
  });

  it('filters by city name', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    await userEvent.type(screen.getByLabelText('Filter cities'), 'chen');

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(within(options[0]).getByText('Chennai')).toBeInTheDocument();
  });

  it('filters by state as well', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    await userEvent.type(screen.getByLabelText('Filter cities'), 'kerala');

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(within(options[0]).getByText('Kochi')).toBeInTheDocument();
  });

  it('says so when nothing matches, rather than showing an empty list', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    await userEvent.type(screen.getByLabelText('Filter cities'), 'atlantis');

    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByText(/No city matches/)).toBeInTheDocument();
  });

  it('clears the filter when the menu is reopened', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    await userEvent.type(screen.getByLabelText('Filter cities'), 'chen');
    await userEvent.keyboard('{Escape}');
    await open();

    expect(screen.getByLabelText('Filter cities')).toHaveValue('');
    expect(screen.getAllByRole('option')).toHaveLength(CITIES.length);
  });
});

describe('selection', () => {
  it('reports the chosen city and closes', async () => {
    const onSelect = vi.fn();
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={onSelect} />);
    await open();
    await userEvent.click(screen.getByRole('option', { name: /Mumbai/ }));

    expect(onSelect).toHaveBeenCalledWith(CITIES[2]);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('marks the current city as selected', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    expect(screen.getByRole('option', { name: /Agra/ })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('option', { name: /Mumbai/ })).toHaveAttribute(
      'aria-selected',
      'false',
    );
  });
});

describe('dismissal', () => {
  it('closes on Escape', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    await open();
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes on an outside click', async () => {
    render(
      <div>
        <CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />
        <button type="button">elsewhere</button>
      </div>,
    );
    await open();
    await userEvent.click(screen.getByRole('button', { name: 'elsewhere' }));
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});

describe('accessibility', () => {
  it('declares the menu relationship and expanded state', async () => {
    render(<CitySelector cities={CITIES} selectedCity={SELECTED} onSelect={vi.fn()} />);
    const trigger = screen.getByRole('button');
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    await open();
    expect(screen.getByRole('button', { expanded: true })).toBeInTheDocument();
  });

  it('renders nothing without a selected city', () => {
    const { container } = render(
      <CitySelector cities={CITIES} selectedCity={null} onSelect={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
