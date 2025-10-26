#Maintainer: Panda <panda@bredos.org>

pkgname=python-bredos-common
pkgver=1.8.3
pkgrel=1
depends=('python>=3.12' 'python-pyrunning' 'python-pysetting' 'pyalpm')
url="https://github.com/BredOS/python-common"
license=('GPLv3')
arch=('any')
makedepends=('python-setuptools' 'python-pipenv')
pkgdesc="Common python functions used in BredOS applications"

build() {
    cd $srcdir/..
    python setup.py build
}

package() {
    install -Dm644 $srcdir/../LICENSE $pkgdir/usr/share/licenses/$pkgname/LICENSE
    cd $srcdir/..
    python setup.py install --root=$pkgdir --optimize=1 --skip-build
}
