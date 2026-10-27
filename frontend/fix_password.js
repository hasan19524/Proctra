const fs = require('fs');
const p = 'src/components/meeting/prejoin-lobby.tsx';
let c = fs.readFileSync(p, 'utf8');
if (!c.includes('const [password')) {
  c = c.replace('  const [cameraOn, setCameraOn] = React.useState(true);\n  const [isAcquiring, setIsAcquiring] = React.useState(true);',
    '  const [cameraOn, setCameraOn] = React.useState(true);\n  const [password, setPassword] = React.useState("");\n  const [isAcquiring, setIsAcquiring] = React.useState(true);');
}
fs.writeFileSync(p, c);
console.log(c.includes('const [password'));
