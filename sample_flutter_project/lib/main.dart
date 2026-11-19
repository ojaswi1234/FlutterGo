import 'package:flutter/material.dart';

void main() => runApp(const RuntimeProbeApp());

class RuntimeProbeApp extends StatelessWidget {
  const RuntimeProbeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flutter Go Runtime Probe',
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      home: const ProbeHomePage(),
    );
  }
}

class ProbeHomePage extends StatefulWidget {
  const ProbeHomePage({super.key});

  @override
  State<ProbeHomePage> createState() => _ProbeHomePageState();
}

class _ProbeHomePageState extends State<ProbeHomePage> {
  int _counter = 0;
  String _assetText = 'Asset not loaded yet';

  Future<void> _loadAsset() async {
    final value = await DefaultAssetBundle.of(context)
        .loadString('assets/message.txt');
    if (!mounted) return;
    setState(() => _assetText = value);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Flutter Go — Runtime Probe')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('External project execution test'),
              const SizedBox(height: 12),
              Text('Counter: $_counter',
                  style: Theme.of(context).textTheme.headlineMedium),
              const SizedBox(height: 12),
              FilledButton(
                onPressed: () => setState(() => _counter++),
                child: const Text('Increment'),
              ),
              OutlinedButton(
                onPressed: _loadAsset,
                child: const Text('Load project asset'),
              ),
              const SizedBox(height: 12),
              Text(_assetText, textAlign: TextAlign.center),
            ],
          ),
        ),
      ),
    );
  }
}
