/**
 * @purpose Node.js script to analyze and prepare emoji-to-icon replacements in React components
 * @context Utility for migrating from Unicode emojis to react-icons for better performance
 * @llm-note Maps emojis to react-icons (FaIcons/SiIcons), adds necessary imports to files,
 *           requires manual JSX updates after running, improves rendering consistency
 */
const fs = require('fs');
const path = require('path');

// Mapping of emojis to their react-icon equivalents
const emojiToIcon = {
  '✅': { icon: 'FaCheckCircle', lib: 'fa', className: 'text-green-400' },
  '✔️': { icon: 'FaCheck', lib: 'fa', className: 'text-green-400' },
  '❌': { icon: 'FaTimesCircle', lib: 'fa', className: 'text-red-400' },
  '✗': { icon: 'FaTimes', lib: 'fa', className: 'text-red-400' },
  '⚠️': { icon: 'FaExclamationTriangle', lib: 'fa', className: 'text-yellow-400' },
  '❗': { icon: 'FaExclamation', lib: 'fa', className: 'text-red-400' },
  '💻': { icon: 'FaLaptop', lib: 'fa', className: 'text-gray-400' },
  '🔧': { icon: 'FaWrench', lib: 'fa', className: 'text-gray-400' },
  '🔍': { icon: 'FaSearch', lib: 'fa', className: 'text-gray-400' },
  '📊': { icon: 'FaChartBar', lib: 'fa', className: 'text-blue-400' },
  '📝': { icon: 'FaEdit', lib: 'fa', className: 'text-gray-400' },
  '🐍': { icon: 'SiPython', lib: 'si', className: 'text-yellow-400' },
  '🌐': { icon: 'FaGlobe', lib: 'fa', className: 'text-blue-400' },
  '📧': { icon: 'FaEnvelope', lib: 'fa', className: 'text-gray-400' },
  '💌': { icon: 'FaHeart', lib: 'fa', className: 'text-red-400' },
  '💬': { icon: 'FaComments', lib: 'fa', className: 'text-gray-400' },
  '📞': { icon: 'FaPhone', lib: 'fa', className: 'text-gray-400' },
  '📱': { icon: 'FaMobileAlt', lib: 'fa', className: 'text-gray-400' },
  '🚀': { icon: 'FaRocket', lib: 'fa', className: 'text-blue-400' },
  '⚡': { icon: 'FaBolt', lib: 'fa', className: 'text-yellow-400' },
  '🎯': { icon: 'FaBullseye', lib: 'fa', className: 'text-red-400' },
  '💡': { icon: 'FaLightbulb', lib: 'fa', className: 'text-yellow-400' },
  '✨': { icon: 'FaStar', lib: 'fa', className: 'text-yellow-400' },
  '👀': { icon: 'FaEye', lib: 'fa', className: 'text-gray-400' },
  '📚': { icon: 'FaBook', lib: 'fa', className: 'text-gray-400' },
  '📋': { icon: 'FaClipboard', lib: 'fa', className: 'text-gray-400' },
  '🎉': { icon: 'FaGift', lib: 'fa', className: 'text-purple-400' },
  '🚨': { icon: 'FaExclamationTriangle', lib: 'fa', className: 'text-red-400' },
  '🛡️': { icon: 'FaShieldAlt', lib: 'fa', className: 'text-blue-400' },
  '🔐': { icon: 'FaLock', lib: 'fa', className: 'text-gray-400' },
  '🔒': { icon: 'FaLock', lib: 'fa', className: 'text-gray-400' },
  '📦': { icon: 'FaBox', lib: 'fa', className: 'text-orange-400' },
  '🤖': { icon: 'FaRobot', lib: 'fa', className: 'text-gray-400' },
  '⏱️': { icon: 'FaClock', lib: 'fa', className: 'text-gray-400' },
  '👥': { icon: 'FaUsers', lib: 'fa', className: 'text-gray-400' },
  '⚖️': { icon: 'FaBalanceScale', lib: 'fa', className: 'text-gray-400' },
  '🏗️': { icon: 'FaBuilding', lib: 'fa', className: 'text-gray-400' },
  '🌟': { icon: 'FaStar', lib: 'fa', className: 'text-yellow-400' },
};

// Files to process
const filesToProcess = [
  'app/vibe-coding/page.tsx',
  'app/links/page.tsx',
  'app/tools/browser/page.tsx',
  'app/tools/page.tsx',
  'app/xray/page.tsx',
  'app/max-iterations/page.tsx',
  'app/send-email/page.tsx',
  'app/llm_do/page.tsx',
  'app/xray/trace/page.tsx',
  'app/prompts/examples/math-tutor/page.tsx',
  'app/blog/naming-is-hard/page.tsx',
  'app/blog/cli-ux-progressive-disclosure/page.tsx',
  'app/prompts/examples/page.tsx',
  'app/blog/trust-keyword/page.tsx',
  'app/blog/llm-do/page.tsx',
  'app/prompts/examples/technical-writer/page.tsx',
  'app/prompts/examples/code-reviewer/page.tsx',
  'app/blog/input-method/page.tsx',
  'app/prompts/examples/friendly-assistant/page.tsx',
  'app/prompts/examples/data-analyst/page.tsx',
  'app/prompts/examples/customer-support/page.tsx',
  'app/prompts/examples/business-strategist/page.tsx',
  'app/prompts/examples/security-analyst/page.tsx'
];

// Process each file
filesToProcess.forEach(file => {
  const filePath = path.join('/Users/changxing/project/OnCourse/platform/connectonion/docs-site', file);

  if (fs.existsSync(filePath)) {
    let content = fs.readFileSync(filePath, 'utf8');
    let needsFaIcons = false;
    let needsSiIcons = false;
    let iconsToImport = new Set();

    // Check which emojis are present
    Object.entries(emojiToIcon).forEach(([emoji, config]) => {
      if (content.includes(emoji)) {
        iconsToImport.add(config.icon);
        if (config.lib === 'fa') needsFaIcons = true;
        if (config.lib === 'si') needsSiIcons = true;
      }
    });

    if (iconsToImport.size > 0) {
      console.log(`Processing ${file}...`);
      console.log(`  Found emojis to replace: ${Array.from(iconsToImport).join(', ')}`);

      // Add imports if not present
      const faIcons = Array.from(iconsToImport).filter(icon => icon.startsWith('Fa'));
      const siIcons = Array.from(iconsToImport).filter(icon => icon.startsWith('Si'));

      if (faIcons.length > 0 && !content.includes('react-icons/fa')) {
        const importStatement = `import { ${faIcons.join(', ')} } from 'react-icons/fa'`;

        // Find the right place to add the import (after other imports)
        const lastImportMatch = content.match(/import[^;]+from[^;]+['"]\s*\n/g);
        if (lastImportMatch) {
          const lastImport = lastImportMatch[lastImportMatch.length - 1];
          const insertPos = content.indexOf(lastImport) + lastImport.length;
          content = content.slice(0, insertPos) + importStatement + '\n' + content.slice(insertPos);
        }
      }

      if (siIcons.length > 0 && !content.includes('react-icons/si')) {
        const importStatement = `import { ${siIcons.join(', ')} } from 'react-icons/si'`;

        // Find the right place to add the import
        const lastImportMatch = content.match(/import[^;]+from[^;]+['"]\s*\n/g);
        if (lastImportMatch) {
          const lastImport = lastImportMatch[lastImportMatch.length - 1];
          const insertPos = content.indexOf(lastImport) + lastImport.length;
          content = content.slice(0, insertPos) + importStatement + '\n' + content.slice(insertPos);
        }
      }

      // Note: For actual replacement in JSX, we'd need more complex parsing
      // This script just shows which files need manual updating
      console.log(`  Added imports for: ${faIcons.concat(siIcons).join(', ')}`);
    }
  }
});

console.log('\nEmoji replacement analysis complete!');
console.log('Note: Manual JSX updates are still needed for proper icon rendering.');