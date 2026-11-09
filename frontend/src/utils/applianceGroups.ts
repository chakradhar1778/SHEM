/** Friendly grouping of appliance icon types used in summaries ("6 Bulbs", "3 Fans"). */
const GROUP: Record<string, { key: string; plural: string }> = {
  bulb: { key: 'bulb', plural: 'Bulbs' },
  cfl: { key: 'bulb', plural: 'Bulbs' },
  lamp: { key: 'lamp', plural: 'Lights' },
  tube: { key: 'tube', plural: 'Tubelight' },
  fan: { key: 'fan', plural: 'Fans' },
  ac: { key: 'ac', plural: 'AC' },
  heater: { key: 'heater', plural: 'Heater' },
  fridge: { key: 'fridge', plural: 'Fridge' },
  tv: { key: 'tv', plural: 'TV' },
  pot: { key: 'pot', plural: 'Cooktop' },
  washer: { key: 'washer', plural: 'Washer' },
  microwave: { key: 'microwave', plural: 'Microwave' },
  mixer: { key: 'mixer', plural: 'Mixer' },
  purifier: { key: 'purifier', plural: 'Purifier' },
  dishwasher: { key: 'dishwasher', plural: 'Dishwasher' },
};

export function groupOf(iconType: string): { key: string; plural: string } {
  return GROUP[iconType] ?? { key: iconType, plural: 'Other' };
}

/** Icon types shown as columns in the quick-add room grid, mapped to a catalogue entry. */
export const GRID_COLUMNS: { label: string; icon: string; catalogueId: string }[] = [
  { label: 'Bulb', icon: 'bulb', catalogueId: 'light-led-philips' },
  { label: 'Tubelight', icon: 'tube', catalogueId: 'light-tube' },
  { label: 'Fan', icon: 'fan', catalogueId: 'fan-standard' },
  { label: 'Heater', icon: 'heater', catalogueId: 'heat-geyser-15' },
  { label: 'AC', icon: 'ac', catalogueId: 'ac-inverter-1-5' },
];

/** Icon for a backend category id (cooling, lighting, …). */
export function iconForCategory(categoryId: string): string {
  const id = categoryId.toLowerCase();
  if (id.includes('cool')) return 'ac';
  if (id.includes('light')) return 'bulb';
  if (id.includes('fan')) return 'fan';
  if (id.includes('refrig') || id.includes('fridge')) return 'fridge';
  if (id.includes('entert') || id.includes('tv')) return 'tv';
  if (id.includes('kitchen')) return 'pot';
  if (id.includes('heat')) return 'heater';
  if (id.includes('wash')) return 'washer';
  if (id.includes('purif')) return 'purifier';
  return 'bulb';
}
