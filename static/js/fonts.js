export const FONT_FAMILIES = [
  { value: 'Nunito', label: 'Nunito (rounded)' },
  { value: 'Poppins', label: 'Poppins' },
  { value: 'Inter', label: 'Inter' },
  { value: 'Space Grotesk', label: 'Space Grotesk' },
  { value: 'Playfair Display', label: 'Playfair Display' },
  { value: 'Bebas Neue', label: 'Bebas Neue' },
  { value: 'Archivo Black', label: 'Archivo Black' },
  { value: 'Caveat', label: 'Caveat' },
  { value: 'Monoton', label: 'Monoton' },
];

export const FONT_WEIGHTS = [
  { value: 400, label: 'Regular' },
  { value: 500, label: 'Medium' },
  { value: 600, label: 'SemiBold' },
  { value: 700, label: 'Bold' },
  { value: 800, label: 'ExtraBold' },
  { value: 900, label: 'Black' },
];

export function templateFontFamilies(template) {
  const set = new Set();
  (template && Array.isArray(template.elements) ? template.elements : []).forEach((element) => {
    if (element && element.font && element.font.family) {
      set.add(element.font.family);
    }
  });
  return Array.from(set);
}

export async function loadFonts(families) {
  const list = Array.isArray(families) ? families : [];
  await Promise.allSettled(list.map(async (family) => {
    try {
      await document.fonts.load(`400 40px "${family}"`);
      await document.fonts.load(`700 40px "${family}"`);
      await document.fonts.load(`900 40px "${family}"`);
    } catch (error) {}
  }));
}
