const SAMPLES = [
  {
    id: 'indie-night',
    label: 'Indie Night',
    description: 'Long artist names, big minutes number.',
    data: {
      artists: [
        'The Decemberists and the Long Avant-Garde Ensemble',
        'Snail Mail',
        'Alvvays',
        'The Strokes',
        'Fleet Foxes',
      ],
      tracks: [
        'Night Shift with the Whole Brass Section Live',
        'Party Police (feat. two long features)',
        'Dreams Tonite',
        'Ode to a Broken String Instrument',
        'Ritual Union',
      ],
      minutes: '53,291',
      genre: 'Indie Folk & Dream Pop',
    },
  },
  {
    id: 'big-number',
    label: 'Power User',
    description: 'A massive listen count for stat overflow.',
    data: {
      artists: [
        'Radiohead',
        'Pink Floyd',
        'King Gizzard & The Lizard Wizard',
        'Beyoncé',
        'Kendrick Lamar',
      ],
      tracks: [
        'Weird Fishes / Arpeggi',
        'Echoes',
        'The River',
        'PLASTIC OFF THE SOFA',
        'Money Trees',
      ],
      minutes: '2,140,607',
      genre: 'Progressive Rock',
    },
  },
  {
    id: 'short-names',
    label: 'Short & Sweet',
    description: 'Tight, short names and a tidy count.',
    data: {
      artists: [
        'Frank',
        'Vega',
        'Crumb',
        'Neutral Milk Hotel',
        'Faye Webster',
      ],
      tracks: [
        'Play it Cool',
        'Melt',
        'Fever',
        'In the Aeroplane',
        'Better Distractions',
      ],
      minutes: '4,213',
      genre: 'Lo-fi',
    },
  },
  {
    id: 'single-name',
    label: 'One Word',
    description: 'A single long artist name at the top.',
    data: {
      artists: [
        'Faye Webster',
        'Frankie Cosmos',
        'Weyes Blood',
        'boygenius',
        'And Their Longest Combined Band Name Here',
      ],
      tracks: [
        'Kingston',
        'Moving Out',
        'Something to Believe',
        'Me & My Dog',
        'Sunsets With the Window Down',
      ],
      minutes: '12,834',
      genre: 'No genre',
    },
  },
  {
    id: 'genre-lead',
    label: 'Genre Lead',
    description: 'An extra-long top genre label.',
    data: {
      artists: [
        'Joanna Newsom',
        'The Microphones',
        'Animal Collective',
        'Duster',
        'Grouper',
      ],
      tracks: [
        'Clover Kingdom in a Field of Dreams',
        'The Moon',
        'Asterisk',
        'Stratosphere',
        'Heavy Water',
      ],
      minutes: '87,004',
      genre: 'Experimental Folk Ambient Drone',
    },
  },
];

export function getSampleSamples() {
  return SAMPLES.map((sample) => ({ id: sample.id, label: sample.label, description: sample.description }));
}

export function getSampleData(id) {
  return SAMPLES.find((sample) => sample.id === id) || SAMPLES[0];
}

export { SAMPLES };
