import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';

class PairingScreen extends StatefulWidget {
  const PairingScreen({super.key});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  final _codeController = TextEditingController();

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _pair() async {
    final code = _codeController.text.trim();
    if (code.length != 9) return;
    final auth = context.read<AuthProvider>();
    final success = await auth.pairChild(code, auth.user!.id);
    if (!mounted) return;
    if (success) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Child paired successfully!')),
      );
      Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    return Scaffold(
      appBar: AppBar(title: const Text('Pair Device')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.link, size: 48),
            const SizedBox(height: 16),
            Text('Pair with Child Device', style: Theme.of(context).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text('Enter the 8-character pairing code shown on your child\'s device'),
            const SizedBox(height: 24),
            TextFormField(
              controller: _codeController,
              textCapitalization: TextCapitalization.characters,
              decoration: const InputDecoration(
                labelText: 'Pairing Code',
                hintText: 'XXXX-XXXX',
                prefixIcon: Icon(Icons.qr_code),
              ),
              maxLength: 9,
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: (_codeController.text.trim().length == 9 && !auth.isLoading) ? _pair : null,
                child: auth.isLoading ? const CircularProgressIndicator(strokeWidth: 2, color: Colors.white) : const Text('Pair Device'),
              ),
            ),
            if (auth.error != null) ...[
              const SizedBox(height: 12),
              Text(auth.error!, style: const TextStyle(color: Colors.red)),
            ],
          ],
        ),
      ),
    );
  }
}
